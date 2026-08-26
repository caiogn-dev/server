"""
Services for automatic print job generation and agent orchestration.
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.stores.models import StoreOrder, StorePrintAgent, StorePrintJob

logger = logging.getLogger(__name__)


# Largura/altura máxima do selo no papel de 80mm. 96 dots ~ 12mm: grande o
# bastante para reconhecer a loja de longe, pequeno o bastante para não comer
# meia comanda. Múltiplo de 8 porque o GS v 0 empacota 8 pixels por byte.
LOGO_MAX_DOTS = 96
LOGO_CACHE_SECONDS = 60 * 60 * 24


def build_store_logo_escpos(store) -> dict | None:
    """Logo da loja como bitmap 1 bit, pronto para o `GS v 0` do print agent.

    A conversão vive aqui, e não no agent, por três motivos: o Pillow já está
    instalado, o resultado é cacheável por loja, e o agent continua sem
    dependência de imagem — ele só decodifica base64 e despeja os bytes.

    Devolve None quando a loja não tem logo; o agent cai no nome em corpo
    duplo e a comanda sai igual.
    """
    logo_file = getattr(store, 'logo', None)
    if not logo_file:
        return None

    # O nome do arquivo entra na chave: trocar a logo no painel gera um nome
    # novo, então o cache velho é abandonado sozinho.
    cache_key = f'print:logo:{store.pk}:{LOGO_MAX_DOTS}:{logo_file.name}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    result = None
    try:
        from PIL import Image, ImageOps

        with logo_file.open('rb') as fh:
            image = Image.open(fh)
            image.load()

        # PNG com transparência vira preto sólido no 'L' se não achatar antes.
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            image = Image.alpha_composite(
                Image.new('RGBA', image.size, (255, 255, 255, 255)), image
            )

        image = ImageOps.autocontrast(image.convert('L'), cutoff=2)

        ratio = min(LOGO_MAX_DOTS / image.width, LOGO_MAX_DOTS / image.height)
        width = max(8, (int(image.width * ratio) // 8) * 8)
        height = max(1, int(image.height * ratio))
        image = image.resize((width, height), Image.LANCZOS)

        # convert('1') aplica Floyd-Steinberg: sem dithering, foto vira mancha.
        bitmap = image.convert('1').tobytes()
        # No Pillow o bit 1 é branco; no ESC/POS o bit 1 é ponto impresso.
        inverted = bytes((~b) & 0xFF for b in bitmap)

        if len(inverted) == (width // 8) * height:
            result = {
                'width': width,
                'height': height,
                'data': base64.b64encode(inverted).decode('ascii'),
            }
    except Exception as exc:  # noqa: BLE001 — logo quebrada não pode derrubar comanda
        logger.warning('Logo ESC/POS falhou para a loja %s: %s', store.pk, exc)

    cache.set(cache_key, result or {}, LOGO_CACHE_SECONDS)
    return result


def _money(value: Decimal | int | float | str | None) -> str:
    number = Decimal(str(value or 0))
    return f"{number:.2f}"


def _extract_address_lines(order: StoreOrder) -> list[str]:
    if order.delivery_method == StoreOrder.DeliveryMethod.PICKUP:
        return ['PEDIDO PARA RETIRADA']

    address = order.delivery_address or {}
    if not isinstance(address, dict):
        return [str(address)]

    line1 = ', '.join(filter(None, [
        address.get('rua') or address.get('street'),
        f"nº {address.get('numero') or address.get('number')}" if address.get('numero') or address.get('number') else '',
    ]))
    line2 = ' - '.join(filter(None, [
        address.get('complemento') or address.get('complement'),
        address.get('bairro') or address.get('neighborhood'),
    ]))
    line3 = ' / '.join(filter(None, [
        address.get('cidade') or address.get('city'),
        address.get('estado') or address.get('state'),
        address.get('cep') or address.get('zip_code'),
    ]))

    # O fallback (endereço em string única) só entra quando os campos
    # estruturados estão vazios — senão a comanda sai com o endereço 2x.
    structured = [line for line in [line1, line2, line3] if line]
    if structured:
        return structured
    fallback = address.get('raw_address') or address.get('address')
    return [fallback] if fallback else []


def _address_warning_lines(order: StoreOrder) -> list[str]:
    """Aviso de endereço divergente (pin do mapa longe do que o cliente escreveu).

    Só serve se chegar antes da moto sair, então vai no papel, não só na tela.
    """
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    divergencia = metadata.get('endereco_divergente')
    if not isinstance(divergencia, dict):
        return []
    digitado = str(divergencia.get('digitado') or '').strip()
    pin = str(divergencia.get('pin') or '').strip()
    if not digitado or not pin:
        return []
    return [
        '!! CONFERIR ENDERECO ANTES DE SAIR !!',
        f'Cliente escreveu: {digitado}',
        f'Pin do mapa cai em: {pin}',
    ]


def _ingredient_lines(ingredients) -> list[str]:
    lines: list[str] = []
    for ingredient in ingredients:
        if isinstance(ingredient, dict):
            name = str(ingredient.get('name') or '').strip()
            if not name:
                continue
            role = str(ingredient.get('role') or '').strip()
            price = Decimal(str(ingredient.get('price') or 0))
            prefix = f"{role}: " if role else ''
            suffix = f" (+R$ {_money(price)})" if price > 0 else ''
            lines.append(f"{prefix}{name}{suffix}")
        elif isinstance(ingredient, str) and ingredient.strip():
            lines.append(ingredient.strip())
    return lines


def _combo_selection_lines(display_data: dict) -> list[str]:
    """Linhas das opções escolhidas no combo (saladas/sabores) p/ a comanda.

    Lê display_data['groups'] (snapshot do checkout). Cada item pode ser uma
    VARIANTE (variant_name) ou um PRODUTO (product_name) — antes a comanda só
    olhava 'ingredients' e não mostrava nada do que o cliente escolheu.
    """
    lines: list[str] = []
    groups = display_data.get('groups') if isinstance(display_data, dict) else None
    for group in (groups or []):
        if not isinstance(group, dict):
            continue
        g_name = str(group.get('group_name') or '').strip()
        group_items = [it for it in (group.get('items') or []) if isinstance(it, dict)]
        if not group_items:
            continue
        if g_name:
            lines.append(f"{g_name.rstrip(':')}:")
        for it in group_items:
            name = str(it.get('product_name') or it.get('variant_name') or '').strip()
            if not name:
                continue
            qty = it.get('quantity') or 1
            lines.append(f"  {qty}x {name}")
    return lines


# ── Comanda de PREPARO ────────────────────────────────────────────────────────
# A comanda de entrega responde "o que sai"; a de preparo responde "o que se
# monta". Para a Ivoneth Banqueteria a diferença é o pedido inteiro: "2x Mini
# Hambúrguer" são 100 unidades, e "trio entradas 20 pessoas" são três terrines
# distintas. O catálogo já sabia disso na descrição do produto — só não
# imprimia.

# Só contagem de ITENS conta como rendimento. `500g` é peso e `R$ 43.60` é
# preço; ambos aparecem em descrição e nenhum diz quanto a cozinha produz.
_UNIDADES_DE_RENDIMENTO = (
    'unidades', 'unidade', 'pessoas', 'pessoa', 'porcoes', 'porções', 'porção', 'porcao',
)

_RENDIMENTO_RE = re.compile(
    r'(?<![\d,.])(\d{1,4})\s*(' + '|'.join(_UNIDADES_DE_RENDIMENTO) + r')\b',
    re.IGNORECASE,
)


def rendimento_por_embalagem(descricao: str | None) -> tuple[int, str] | None:
    """Quantos itens UMA unidade vendida rende, lido da descrição do catálogo.

    Reconhece as duas formas que a Ivoneth usa na prática:
      "Vendido em embalagem com 50 unidades."  -> (50, 'unidades')
      "100 unidades de brigadeiro caseiro."    -> (100, 'unidades')

    Devolve None quando não há contagem — o que é o caso da maioria das lojas.
    Sem isso, a comanda passaria a imprimir texto de marketing como se fosse
    instrução de preparo.
    """
    if not descricao:
        return None
    achado = _RENDIMENTO_RE.search(str(descricao))
    if not achado:
        return None
    return int(achado.group(1)), achado.group(2).lower()


def _limpa_markdown_whatsapp(texto: str) -> str:
    """`*delicioso*` é negrito no WhatsApp e ruído no papel térmico."""
    return re.sub(r'[*_~`]', '', texto)


# Sinais de que a linha foi escrita para VENDER, não para montar. Rodando a
# regra contra o catálogo real, sem este filtro a comanda da cozinha saía com
# "Com 15% de desconto!", "Economize: R$ 43.60" e "Peça agora e não fique de
# fora dessa promoção!". Papel térmico é caro; atenção de cozinha em sábado de
# evento é mais ainda.
_MARKETING = re.compile(
    r'R\$|%|\bdesconto|\beconomiz|\bpromo|\bpeça agora|\baproveite|\bperfeito para'
    r'|\bnão fique|\bpara quem ama|\bpara sua vida|\bpara o seu dia|\bpronto para o consumo'
    r'|\bdividir com|\bagilidade|\bpraticidade|\bde graça',
    re.IGNORECASE,
)

# Uma linha vale para a cozinha quando carrega QUANTIDADE ("120 g", "1
# terrine", "500g") ou quando é um nome curto de item ("chocolate e ninho").
# Frase longa sem número é quase sempre texto de venda.
_TEM_QUANTIDADE = re.compile(r'\d\s*(g|kg|ml|l|un|und|unid)\b|^\s*\d+\s+\S', re.IGNORECASE)
_LIMITE_NOME_CURTO = 42


def _linha_serve_para_montar(linha: str) -> bool:
    if _MARKETING.search(linha):
        return False
    if _TEM_QUANTIDADE.search(linha):
        return True
    return len(linha) <= _LIMITE_NOME_CURTO and not linha.endswith('!')


# Uma linha só vira ficha técnica quando é mesmo uma LISTA. Duas vírgulas numa
# frase ("Bolo recheado, feito na hora.") não fazem dela composição, então o
# corte é em 3 pedaços úteis.
_MINIMO_DE_ITENS_NA_LISTA = 3


def _quebra_lista_em_uma_linha(linha: str) -> list[str]:
    """Separa "Provolone, parmesão, ... , tomate seco e snacks" em itens.

    A Tábua de Frios — o item mais caro do pedido da Fabiana — tem a
    composição inteira numa linha só. Exigir quebra de linha empurrava a conta
    para o dono ("recadastre o produto"); o separador da lista é a vírgula.

    Devolve [] quando não é lista, para o chamador seguir tratando como frase.
    """
    cabecalho, _, corpo = linha.partition(':')
    if not corpo.strip():
        # Sem cabeçalho, um ponto final NO MEIO denuncia frase, não lista:
        # "Porção de 35 g. Repolho finamente fatiado, fresco, crocante" emenda
        # duas orações, e a vírgula ali separa ADJETIVO. Quebrar isso mandava
        # a cozinha "montar" fresco e crocante. Uma ficha de verdade
        # ("Provolone, parmesão, gorgonzola") não tem ponto no meio.
        if re.search(r'\.\s+\S', linha):
            return []
        cabecalho, corpo = '', linha

    itens = [p.strip(' .;') for p in corpo.split(',')]
    itens = [p for p in itens if p]
    if not itens:
        return []

    # O ÚLTIMO separador de uma lista em português é " e ", não vírgula:
    # "tomate seco e snacks" são dois frios. Só o último pedaço é quebrado —
    # no meio, " e " pertence ao item ("terrine de gorgonzola e damasco").
    ultimo = itens.pop()
    partes_finais = re.split(r'\s+e\s+|\s+ou\s+', ultimo)
    itens.extend(p.strip(' .;') for p in partes_finais if p.strip(' .;'))

    uteis = [p for p in itens if _linha_serve_para_montar(p)]
    if len(uteis) < _MINIMO_DE_ITENS_NA_LISTA:
        return []

    cabecalho = cabecalho.strip(' .;')
    # O cabeçalho ("Ingredientes", "Sabores") diz o que a lista É; sem ele,
    # "acerola / caju / goiaba" solto na comanda não significa nada.
    return ([f'{cabecalho}:'] if cabecalho and _linha_serve_para_montar(cabecalho) else []) + uteis


def linhas_de_preparo(
    descricao: str | None,
    quantidade: int,
    variante: str | None = None,
    produto: str | None = None,
) -> list[str]:
    """O que a cozinha precisa ler, derivado do cadastro do produto.

    Duas coisas, nesta ordem:

    1. **O rendimento já multiplicado.** `>> 100 UNIDADES (2 x 50)`. A conta de
       cabeça, num sábado de evento, é onde o erro acontece — então a comanda
       faz a conta e mostra a origem dela. Procura primeiro na descrição e, se
       não achar, no nome da variante: a Tábua de Frios guarda o rendimento em
       "Tábua - 20 Pessoas", e sem isso o item mais caro do pedido saía sem
       dizer para quantas pessoas é.
    2. **A composição**, uma linha por item — mas só as linhas que servem para
       montar (ver `_linha_serve_para_montar`).

    Descrição puramente de venda devolve lista vazia de propósito.
    """
    texto = _limpa_markdown_whatsapp(str(descricao or '')).replace('\r\n', '\n').replace('\r', '\n')
    linhas: list[str] = []

    rendimento = rendimento_por_embalagem(texto) or rendimento_por_embalagem(variante)
    if rendimento:
        por_unidade, unidade = rendimento
        qtd = max(int(quantidade or 1), 1)
        total = por_unidade * qtd
        conta = f' ({qtd} x {por_unidade})' if qtd > 1 else ''
        linhas.append(f'>> {total} {unidade.upper()}{conta}')

    # A descrição já pode trazer o próprio marcador ('- Frango 120 g'); somar
    # outro produz '- - Frango 120 g'.
    partes = [l.strip().lstrip('-•·').strip(' .;') for l in texto.split('\n')]
    partes = [l for l in partes if l]

    if len(partes) == 1:
        # Ficha cadastrada numa linha só, separada por vírgula.
        partes = _quebra_lista_em_uma_linha(partes[0])

    if len(partes) > 1:
        nome_do_produto = str(produto or '').strip().casefold()
        for parte in partes:
            # A ficha costuma abrir repetindo o nome do produto, que já está em
            # corpo duplo na linha do item logo acima. Compara por IGUALDADE:
            # descartar por "contém" apagaria "Massa de bolo 300 g" num produto
            # chamado "Bolo".
            if nome_do_produto and parte.strip().casefold() == nome_do_produto:
                continue
            if not _linha_serve_para_montar(parte):
                continue
            # O que já virou a linha `>>` não se repete embaixo dela.
            if rendimento and rendimento_por_embalagem(parte) == rendimento:
                continue
            linhas.append(f'- {parte}')

    return linhas


def _preparo_do_item(item) -> list[str]:
    """`product` é SET_NULL: pedido antigo sobrevive ao produto excluído."""
    produto = getattr(item, 'product', None)
    if produto is None:
        return []
    return linhas_de_preparo(
        getattr(produto, 'description', ''),
        item.quantity,
        variante=getattr(item, 'variant_name', '') or '',
        produto=getattr(produto, 'name', '') or item.product_name,
    )


def build_order_print_payload(order: StoreOrder, *, template: str = StorePrintJob.Template.KITCHEN_TICKET) -> dict:
    # Combos ligados a uma linha de item são pulados no loop de combos abaixo
    # (evita duplicar a linha), então os sabores escolhidos precisam entrar
    # nos details do próprio item — senão a comanda sai sem salada/suco.
    combo_by_order_item = {
        combo.order_item_id: combo
        for combo in order.combo_items.all()
        if getattr(combo, 'order_item_id', None)
    }

    items = []
    for item in order.items.all():
        options = item.options if isinstance(item.options, dict) else {}
        details = []
        if item.variant_name:
            details.append(item.variant_name)
        combo_ingredients = []
        linked_combo = combo_by_order_item.get(item.id)
        if linked_combo is not None:
            linked_display = linked_combo.display_data if isinstance(linked_combo.display_data, dict) else {}
            details.extend(_combo_selection_lines(linked_display))
            # O print-agent atual só imprime 'ingredients' (não lê 'details'),
            # então as escolhas do combo também vão como ingredients.
            for group in (linked_display.get('groups') or []):
                if not isinstance(group, dict):
                    continue
                role = str(group.get('group_name') or '').strip().rstrip(':')
                for sel in (group.get('items') or []):
                    if not isinstance(sel, dict):
                        continue
                    name = str(sel.get('product_name') or sel.get('variant_name') or '').strip()
                    if name:
                        qty = sel.get('quantity') or 1
                        combo_ingredients.append({'role': role, 'name': f"{qty}x {name}" if qty > 1 else name, 'price': 0})
        details.extend(_ingredient_lines(options.get('ingredients') or []))
        items.append({
            'type': 'item',
            'qty': item.quantity,
            'name': item.product_name,
            'unit_price': _money(item.unit_price),
            'subtotal': _money(item.subtotal),
            'details': details,
            'ingredients': combo_ingredients,
            # O que a cozinha monta, não o que o cliente recebe. Ver
            # `linhas_de_preparo`.
            'prep': _preparo_do_item(item),
            'notes': item.notes or '',
        })

    for combo in order.combo_items.all():
        if getattr(combo, 'order_item_id', None):
            continue
        display_data = combo.display_data if isinstance(combo.display_data, dict) else {}
        customizations = display_data.get('customizations') if isinstance(display_data.get('customizations'), dict) else {}
        unit_price = display_data.get('unit_price') or 0
        items.append({
            'type': 'combo',
            'qty': combo.quantity,
            'name': display_data.get('combo_name') or (combo.combo.name if combo.combo else 'Combo'),
            'unit_price': _money(unit_price),
            'subtotal': _money(combo.subtotal),
            'details': [
                'COMBO',
                *_combo_selection_lines(display_data),
                *_ingredient_lines(customizations.get('ingredients') or []),
            ],
            'notes': '',
        })

    scheduled_for = ' '.join(filter(None, [
        order.scheduled_date.isoformat() if order.scheduled_date else '',
        order.scheduled_time or '',
    ])).strip()

    return {
        'template': template,
        'generated_at': timezone.now().isoformat(),
        'store': {
            'id': str(order.store_id),
            'name': order.store.name,
            'logo_escpos': build_store_logo_escpos(order.store),
            'slug': order.store.slug,
            'phone': order.store.phone or order.store.whatsapp_number or '',
            'address': order.store.address or '',
            'city': order.store.city or '',
            'state': order.store.state or '',
        },
        'order': {
            'id': str(order.id),
            'order_number': order.order_number,
            'created_at': order.created_at.isoformat(),
            'scheduled_for': scheduled_for,
            'delivery_method': order.delivery_method,
            'payment_method': order.payment_method or '',
            'payment_status': order.payment_status,
            'status': order.status,
            # Canal de origem: WhatsApp, PDV e site se comportam diferente
            # quando dá problema, e a cozinha lê isso na comanda.
            'source': order.source or '',
            'coupon_code': order.coupon_code or '',
            'customer_notes': order.customer_notes or '',
            'internal_notes': order.internal_notes or '',
            'delivery_notes': order.delivery_notes or '',
        },
        'customer': {
            'name': order.customer_name,
            'phone': order.customer_phone,
            'email': order.customer_email if order.customer_email and not any(order.customer_email.endswith(s) for s in ('@local.invalid', '@whatsapp.bot', '@cliente.pastita.com.br')) else '',
        },
        'address_lines': _extract_address_lines(order),
        # Pin do mapa x endereço escrito. O painel já avisa disso na comanda
        # que ele imprime; sem isto o papel do print agent saía sem o aviso —
        # e é este papel que o entregador leva.
        'address_warning': _address_warning_lines(order),
        'items': items,
        'totals': {
            'subtotal': _money(order.subtotal),
            'discount': _money(order.discount),
            'delivery_fee': _money(order.delivery_fee),
            'total': _money(order.total),
        },
    }


@dataclass(slots=True)
class PrintJobResult:
    job: StorePrintJob
    created: bool


def enqueue_order_print_job(
    order: StoreOrder,
    *,
    station: str = 'kitchen',
    template: str = StorePrintJob.Template.KITCHEN_TICKET,
    source: str = StorePrintJob.Source.ORDER_CREATED,
    dedupe: bool = True,
    requested_by: str = '',
) -> PrintJobResult:
    payload = build_order_print_payload(order, template=template)
    target_agents = list(
        StorePrintAgent.objects.filter(
            store=order.store,
            station=station,
            status=StorePrintAgent.AgentStatus.ACTIVE,
            is_active=True,
        ).order_by('created_at')
    )
    targets: list[StorePrintAgent | None] = target_agents or [None]

    first_result: PrintJobResult | None = None
    any_created = False

    for target_agent in targets:
        dedupe_key = ''
        if dedupe:
            target_part = f":agent:{target_agent.id}" if target_agent else ''
            dedupe_key = f"order:{order.id}:station:{station}:template:{template}:source:{source}{target_part}"

        defaults = {
            'store': order.store,
            'order': order,
            'target_agent': target_agent,
            'station': station,
            'template': template,
            'source': source,
            'payload': payload,
            'title': f"{order.store.name} #{order.order_number}",
            'max_attempts': target_agent.max_retries if target_agent else 3,
            'metadata': {'requested_by': requested_by} if requested_by else {},
        }

        try:
            with transaction.atomic():
                job, created = StorePrintJob.objects.get_or_create(
                    dedupe_key=dedupe_key,
                    defaults=defaults,
                ) if dedupe_key else (StorePrintJob.objects.create(**defaults), True)
        except IntegrityError:
            job = StorePrintJob.objects.get(dedupe_key=dedupe_key)
            created = False

        any_created = any_created or created
        if first_result is None:
            first_result = PrintJobResult(job=job, created=created)

    if first_result is None:
        raise RuntimeError('No print job target resolved')
    return PrintJobResult(job=first_result.job, created=any_created)


def claim_next_print_job(agent: StorePrintAgent) -> StorePrintJob | None:
    with transaction.atomic():
        job = (
            StorePrintJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                store=agent.store,
                station=agent.station,
                status=StorePrintJob.JobStatus.PENDING,
                available_at__lte=timezone.now(),
            )
            .filter(Q(target_agent=agent) | Q(target_agent__isnull=True))
            .order_by('created_at')
            .first()
        )
        if not job:
            return None

        job.claim(agent)
        return job


def complete_print_job(job: StorePrintJob, *, printer_name: str = '', metadata: dict | None = None) -> StorePrintJob:
    job.complete(printer_name=printer_name, metadata=metadata)
    return job


def fail_print_job(
    job: StorePrintJob,
    *,
    error_message: str,
    retryable: bool = True,
    retry_delay_seconds: int = 15,
) -> StorePrintJob:
    job.fail(
        error_message=error_message,
        retryable=retryable,
        retry_delay_seconds=retry_delay_seconds,
    )
    return job
