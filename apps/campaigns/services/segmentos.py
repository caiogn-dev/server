"""Quem recebe a campanha: a régua de segmentação da audiência.

Até 28/ago/2026 o painel mandava `source: 'all'` fixo (`NewWhatsAppCampaignPage.tsx`)
e a única audiência possível era "todos". Campanha para todo mundo é a que mais
queima base: quem comprou ontem recebe "sentimos sua falta" e quem nunca comprou
recebe "peça o seu de sempre". Cada disparo errado gasta uma janela paga da Meta
e empurra a pessoa para o botão "Parar promoções".

QUATRO EIXOS, TODOS DERIVADOS DO PEDIDO

    recência      quando foi a última compra  -> ativo / em risco / inativo / nunca
    frequência    quantas compras já fez      -> novo / ocasional / VIP
    produto       o que a pessoa já pediu     -> recompra do que ela gosta
    ticket/bairro quanto gasta e de onde      -> oferta e frete fazem sentido

POR QUE AGREGAR DE `StoreOrder` E NÃO DE `StoreCustomer`

`StoreCustomer.total_orders` é contador denormalizado, e na Cê Saladas ele cobre
63 dos 73 telefones que já pediram: 10 pessoas reais ficariam invisíveis para
toda campanha. O pedido é o fato, o contador é a cópia — e cópia envelhece.

POR QUE A CHAVE É `chave_do_telefone` E NÃO A STRING CRUA

A mesma pessoa chega com e sem DDI, com e sem o nono dígito. Sem colapsar isso, o
segmento "VIP" quebra em duas metades de 2 e 3 pedidos e ninguém vira VIP. É a
mesma chave usada pela deduplicação de contatos (ver `contatos.py`).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone

from .contatos import chave_do_telefone

# ---------------------------------------------------------------------------
# Réguas. Estas constantes são a ÚNICA fonte: o CRM do painel e o resumo de
# clientes copiavam os mesmos números soltos, e duas cópias viram duas verdades.
# ---------------------------------------------------------------------------

#: Comprou dentro desta janela: a loja ainda está na cabeça da pessoa.
DIAS_ATIVO = 30
#: Passado isto, quem sumiu raramente volta sozinho — vira campanha.
DIAS_RISCO = 45
#: A partir daqui a pessoa é recorrente de verdade, não sorte de duas vezes.
PEDIDOS_VIP = 5
#: Acima de 1 pedido deixa de ser "experimentou" e vira "voltou".
PEDIDOS_OCASIONAL = 2

#: QUEM CONTA COMO CLIENTE é a mesma pergunta que "o que conta como dinheiro",
#: e essa já tem dono: `apps/stores/metrics/definicoes.apenas_receita`.
#:
#: A primeira versão deste módulo tinha a própria lista de status e foi pega
#: pela catraca `test_metrics_sem_matematica_solta` — com razão, e o defeito
#: era pior do que estilo: filtrar por status SEM checar `payment_status`
#: repetia exatamente o bug que o núcleo existe para ter matado (o resumo de
#: IA excluía cancelado mas contava pedido não pago), e não excluía os pedidos
#: de TESTE do dono, que são ~40% do volume. O dono viraria "VIP" da própria
#: loja e receberia a campanha de reativação dele mesmo.
#: A função vem do núcleo com o nome dele: quem lê aqui deve reconhecer de
#: onde a regra veio, e um apelido local só criaria um segundo vocabulário
#: para a mesma coisa.
from apps.stores.metrics.definicoes import pedidos_de_receita  # noqa: E402


class Recencia:
    ATIVO = 'ativo'
    EM_RISCO = 'em_risco'
    INATIVO = 'inativo'
    NUNCA_COMPROU = 'nunca_comprou'

    TODAS = (ATIVO, EM_RISCO, INATIVO, NUNCA_COMPROU)

    ROTULOS = {
        ATIVO: f'comprou nos últimos {DIAS_ATIVO} dias',
        EM_RISCO: f'{DIAS_ATIVO} a {DIAS_RISCO} dias sem comprar',
        INATIVO: f'mais de {DIAS_RISCO} dias sem comprar',
        NUNCA_COMPROU: 'nunca comprou (só conversou)',
    }


class Frequencia:
    NOVO = 'novo'
    OCASIONAL = 'ocasional'
    VIP = 'vip'

    TODAS = (NOVO, OCASIONAL, VIP)

    ROTULOS = {
        NOVO: 'Novo (1 pedido)',
        OCASIONAL: f'Ocasional ({PEDIDOS_OCASIONAL} a {PEDIDOS_VIP - 1} pedidos)',
        VIP: f'VIP ({PEDIDOS_VIP} pedidos ou mais)',
    }


def classificar_recencia(ultima_compra) -> str:
    """`None` é "nunca comprou", não "comprou há muito tempo".

    A diferença decide a mensagem: quem sumiu recebe "volta pra gente", quem
    nunca comprou recebe "primeira compra com desconto". Colapsar os dois no
    mesmo balde manda a oferta errada para metade da lista.
    """
    if ultima_compra is None:
        return Recencia.NUNCA_COMPROU

    dias = (timezone.now() - ultima_compra).days
    if dias <= DIAS_ATIVO:
        return Recencia.ATIVO
    if dias <= DIAS_RISCO:
        return Recencia.EM_RISCO
    return Recencia.INATIVO


def classificar_frequencia(total_pedidos: int) -> Optional[str]:
    """Devolve `None` para quem tem zero pedidos: não é "novo", é "não cliente"."""
    if not total_pedidos:
        return None
    if total_pedidos < PEDIDOS_OCASIONAL:
        return Frequencia.NOVO
    if total_pedidos < PEDIDOS_VIP:
        return Frequencia.OCASIONAL
    return Frequencia.VIP


# ---------------------------------------------------------------------------
# Agregação: um retrato por telefone, montado a partir dos pedidos da loja.
# ---------------------------------------------------------------------------

def perfis_por_telefone(store_ids: Iterable[Any]) -> Dict[str, dict]:
    """Retrato de compra de cada telefone que já pediu nas lojas informadas.

    Uma consulta agregada em `store_orders` (índice `order_store_stat_created_idx`)
    mais uma em `store_order_items` só quando há filtro de produto — porque a
    segunda é a cara e a maioria das campanhas não usa produto.
    """
    from apps.stores.models import StoreOrder

    store_ids = list(store_ids)
    if not store_ids:
        return {}

    linhas = (
        pedidos_de_receita(queryset=StoreOrder.objects.filter(store_id__in=store_ids))
        .exclude(customer_phone='')
        .values('customer_phone')
        .annotate(
            pedidos=models.Count('id'),
            gasto=Coalesce(models.Sum('total'), Decimal('0')),
            ultima=models.Max('created_at'),
        )
    )

    perfis: Dict[str, dict] = {}
    for linha in linhas:
        # A agregação é por string crua; o colapso para a chave canônica é
        # feito aqui, somando as metades da mesma pessoa.
        chave = chave_do_telefone(linha['customer_phone'])
        if not chave:
            continue

        atual = perfis.get(chave)
        if atual is None:
            perfis[chave] = {
                'pedidos': linha['pedidos'],
                'gasto': linha['gasto'],
                'ultima_compra': linha['ultima'],
            }
            continue

        atual['pedidos'] += linha['pedidos']
        atual['gasto'] += linha['gasto']
        if linha['ultima'] and (not atual['ultima_compra'] or linha['ultima'] > atual['ultima_compra']):
            atual['ultima_compra'] = linha['ultima']

    for perfil in perfis.values():
        perfil['recencia'] = classificar_recencia(perfil['ultima_compra'])
        perfil['frequencia'] = classificar_frequencia(perfil['pedidos'])
        perfil['ticket_medio'] = (
            perfil['gasto'] / perfil['pedidos'] if perfil['pedidos'] else Decimal('0')
        )

    return perfis


def chaves_que_pediram_produtos(store_ids: Iterable[Any], product_ids: Iterable[Any]) -> set:
    """Telefones que já compraram pelo menos um dos produtos."""
    from apps.stores.models import StoreOrder

    store_ids, product_ids = list(store_ids), list(product_ids)
    if not store_ids or not product_ids:
        return set()

    telefones = (
        pedidos_de_receita(
            queryset=StoreOrder.objects.filter(
                store_id__in=store_ids, items__product_id__in=product_ids
            )
        )
        .values_list('customer_phone', flat=True)
        .distinct()
    )
    return {chave_do_telefone(t) for t in telefones if chave_do_telefone(t)}


def chaves_dos_bairros(store_ids: Iterable[Any], bairros: Iterable[str]) -> set:
    """Telefones cujo endereço de entrega cai em um dos bairros.

    O bairro mora dentro do JSON `delivery_address` e só existe em 55 dos 76
    endereços da Cê Saladas — quem pediu retirada ou digitou endereço solto
    simplesmente não tem bairro, e por isso NUNCA entra num filtro de bairro.
    Isso é intencional: melhor uma lista menor e certa do que mandar oferta de
    frete grátis do Centro para quem mora do outro lado.
    """
    from apps.stores.models import StoreOrder

    store_ids = list(store_ids)
    alvos = {str(b).strip().casefold() for b in bairros if str(b).strip()}
    if not store_ids or not alvos:
        return set()

    linhas = (
        pedidos_de_receita(queryset=StoreOrder.objects.filter(store_id__in=store_ids))
        .exclude(customer_phone='')
        .values_list('customer_phone', 'delivery_address')
    )

    chaves = set()
    for telefone, endereco in linhas:
        bairro = (endereco or {}).get('neighborhood') if isinstance(endereco, dict) else None
        if bairro and str(bairro).strip().casefold() in alvos:
            chave = chave_do_telefone(telefone)
            if chave:
                chaves.add(chave)
    return chaves


def bairros_disponiveis(store_ids: Iterable[Any]) -> List[dict]:
    """Bairros com pelo menos um pedido, para o painel montar o seletor."""
    from apps.stores.models import StoreOrder

    store_ids = list(store_ids)
    if not store_ids:
        return []

    contagem: Dict[str, dict] = {}
    linhas = (
        pedidos_de_receita(queryset=StoreOrder.objects.filter(store_id__in=store_ids))
        .exclude(customer_phone='')
        .values_list('customer_phone', 'delivery_address')
    )
    for telefone, endereco in linhas:
        bairro = (endereco or {}).get('neighborhood') if isinstance(endereco, dict) else None
        if not bairro or not str(bairro).strip():
            continue
        nome = str(bairro).strip()
        registro = contagem.setdefault(nome.casefold(), {'nome': nome, 'telefones': set()})
        chave = chave_do_telefone(telefone)
        if chave:
            registro['telefones'].add(chave)

    return sorted(
        ({'nome': r['nome'], 'clientes': len(r['telefones'])} for r in contagem.values()),
        key=lambda b: (-b['clientes'], b['nome']),
    )


# ---------------------------------------------------------------------------
# Aplicação dos filtros sobre a lista de contatos já deduplicada.
# ---------------------------------------------------------------------------

def aplicar_filtros(
    contatos: Dict[str, dict],
    perfis: Dict[str, dict],
    filtros: Dict[str, Any],
    chaves_por_produto: Optional[set] = None,
    chaves_por_bairro: Optional[set] = None,
) -> Dict[str, dict]:
    """Devolve só os contatos que passam em TODOS os filtros pedidos.

    Filtros vazios não filtram nada — o "todos" de hoje continua sendo o
    caminho padrão, só que agora é uma escolha e não a única opção.
    """
    recencias = set(filtros.get('recencia') or [])
    frequencias = set(filtros.get('frequencia') or [])
    ticket_min = filtros.get('ticket_min')
    ticket_max = filtros.get('ticket_max')

    selecionados: Dict[str, dict] = {}
    for chave, contato in contatos.items():
        perfil = perfis.get(chave)

        # Quem só conversou não tem perfil de compra: é "nunca comprou".
        recencia = perfil['recencia'] if perfil else Recencia.NUNCA_COMPROU
        frequencia = perfil['frequencia'] if perfil else None
        ticket = perfil['ticket_medio'] if perfil else Decimal('0')

        if recencias and recencia not in recencias:
            continue
        if frequencias and frequencia not in frequencias:
            continue
        # Faixa de ticket sobre quem nunca comprou não tem sentido: sem compra
        # não há ticket, e deixar passar encheria a lista de zeros.
        if (ticket_min is not None or ticket_max is not None) and perfil is None:
            continue
        if ticket_min is not None and ticket < Decimal(str(ticket_min)):
            continue
        if ticket_max is not None and ticket > Decimal(str(ticket_max)):
            continue
        if chaves_por_produto is not None and chave not in chaves_por_produto:
            continue
        if chaves_por_bairro is not None and chave not in chaves_por_bairro:
            continue

        enriquecido = dict(contato)
        enriquecido['recencia'] = recencia
        enriquecido['frequencia'] = frequencia
        enriquecido['pedidos'] = perfil['pedidos'] if perfil else 0
        enriquecido['ticket_medio'] = float(ticket)
        enriquecido['ultima_compra'] = (
            perfil['ultima_compra'].isoformat() if perfil and perfil['ultima_compra'] else None
        )
        selecionados[chave] = enriquecido

    return selecionados


def resumo_por_segmento(contatos: Dict[str, dict], perfis: Dict[str, dict]) -> dict:
    """Quantas pessoas há em cada balde, para o painel mostrar ANTES do envio.

    Sem isso o dono escolhe "inativos" no escuro e só descobre que são 3 pessoas
    depois de montar a campanha inteira.
    """
    recencia = {chave: 0 for chave in Recencia.TODAS}
    frequencia = {chave: 0 for chave in Frequencia.TODAS}

    for chave in contatos:
        perfil = perfis.get(chave)
        recencia[perfil['recencia'] if perfil else Recencia.NUNCA_COMPROU] += 1
        if perfil and perfil['frequencia']:
            frequencia[perfil['frequencia']] += 1

    return {
        'recencia': [
            {'valor': v, 'rotulo': Recencia.ROTULOS[v], 'total': recencia[v]}
            for v in Recencia.TODAS
        ],
        'frequencia': [
            {'valor': v, 'rotulo': Frequencia.ROTULOS[v], 'total': frequencia[v]}
            for v in Frequencia.TODAS
        ],
    }


def descrever_filtros(filtros: Dict[str, Any]) -> str:
    """A frase que o painel mostra: "quem vai receber", em português.

    O número sozinho ("134 contatos") não deixa ninguém conferir se errou o
    filtro. A frase deixa.
    """
    partes: List[str] = []

    for valor in filtros.get('recencia') or []:
        rotulo = Recencia.ROTULOS.get(valor)
        if rotulo:
            partes.append(rotulo)

    for valor in filtros.get('frequencia') or []:
        rotulo = Frequencia.ROTULOS.get(valor)
        if rotulo:
            partes.append(rotulo)

    produtos = filtros.get('produtos_nomes') or []
    if produtos:
        partes.append('já pediu ' + ', '.join(produtos))

    bairros = filtros.get('bairros') or []
    if bairros:
        partes.append('mora em ' + ', '.join(bairros))

    ticket_min, ticket_max = filtros.get('ticket_min'), filtros.get('ticket_max')
    if ticket_min is not None and ticket_max is not None:
        partes.append(f'ticket médio entre R$ {ticket_min} e R$ {ticket_max}')
    elif ticket_min is not None:
        partes.append(f'ticket médio a partir de R$ {ticket_min}')
    elif ticket_max is not None:
        partes.append(f'ticket médio até R$ {ticket_max}')

    if not partes:
        return 'Todos os contatos'
    return ' e '.join(partes)
