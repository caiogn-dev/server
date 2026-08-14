"""Atalhos "/" do inbox: agir no pedido sem sair da conversa.

Nasceu de uma conta de tempo. Em 13/ago o bot montou um pedido errado para a
Yeda, e consertar custou à dona **5 minutos e uma troca de tela**: cancelar o
pedido no painel, refazer o valor, copiar um link do Mercado Pago e colar no
chat — com a cliente esperando do outro lado.

Este módulo é só o INTERPRETADOR. Ele lê o texto e diz o que a pessoa quis
fazer; quem executa é a camada de ação, e quem confirma é a tela. A separação é
a mesma da triagem, e pela mesma razão: interpretar é barato e testável, agir é
irreversível.

O perigo específico desta superfície não é o comando dar errado — é o comando
não ser reconhecido e **virar mensagem enviada ao cliente**. A dona digita
`/pixx`, o sistema não entende, e a cliente recebe "/pixx". Por isso
`enviar_ao_cliente` é False até para o desconhecido: qualquer texto que comece
com barra é tentativa de comando, nunca conversa.
"""
import difflib
import re
from dataclasses import dataclass
from typing import Optional

#: Catálogo. `descricao` não é enfeite: é o que a paleta do painel mostra, e sem
#: ela o atalho vira adivinhação.
COMANDOS = {
    'pedido': {
        'descricao': 'Mostra o resumo do pedido atual do cliente',
        'confirmar': False,
    },
    'pix': {
        'descricao': 'Gera e envia o PIX do pedido atual',
        'confirmar': False,
    },
    'status': {
        'descricao': 'Mostra em que etapa o pedido está',
        'confirmar': False,
    },
    'entregue': {
        'descricao': 'Marca o pedido como entregue e avisa o cliente',
        'confirmar': True,
    },
    'cancelar': {
        'descricao': 'Cancela o pedido atual',
        'confirmar': True,
    },
    'cupom': {
        'descricao': 'Aplica um cupom ao pedido — /cupom CODIGO',
        'confirmar': False,
    },
    'nota': {
        'descricao': 'Anota um recado interno na conversa — /nota texto',
        'confirmar': False,
    },
    'bot': {
        'descricao': 'Liga ou desliga o bot nesta conversa — /bot on | off',
        'confirmar': False,
    },
}


@dataclass
class Comando:
    nome: str
    argumento: str = ''
    conhecido: bool = True
    precisa_confirmar: bool = False
    sugestao: Optional[str] = None
    #: Sempre False. Comando é instrução para o sistema, nunca texto para o
    #: cliente — nem quando o sistema não entendeu.
    enviar_ao_cliente: bool = False


def interpretar(texto: str) -> Optional[Comando]:
    """Devolve o comando, ou None quando a mensagem é conversa normal.

    Só conta barra no INÍCIO. "5/5 estrelas" e "meio/meio" são texto de gente e
    não podem virar comando — o operador digita no mesmo campo em que fala com o
    cliente.
    """
    if not texto:
        return None
    limpo = texto.strip()
    if not limpo.startswith('/'):
        return None

    corpo = limpo[1:].strip()
    if not corpo:
        return None

    partes = re.split(r'\s+', corpo, maxsplit=1)
    nome = partes[0].lower()
    argumento = partes[1].strip() if len(partes) > 1 else ''

    meta = COMANDOS.get(nome)
    if meta is None:
        return Comando(
            nome=nome,
            argumento=argumento,
            conhecido=False,
            sugestao=_parecido(nome),
        )

    return Comando(
        nome=nome,
        argumento=argumento,
        precisa_confirmar=bool(meta['confirmar']),
    )


def _parecido(nome: str) -> Optional[str]:
    """O comando mais próximo, quando existe um.

    Erro de digitação é o caso comum de quem usa atalho com pressa. Sugerir sem
    executar deixa a correção a um toque, sem risco de agir pelo palpite.
    """
    achados = difflib.get_close_matches(nome, COMANDOS.keys(), n=1, cutoff=0.6)
    return achados[0] if achados else None


# ── Execução ──────────────────────────────────────────────────────────────
#
# O interpretador acima existia desde 13/ago e o painel já mostrava a paleta,
# mas a execução respondia "ainda não está ligado — em breve". Ou seja: a dona
# digitava `/pix`, lia um aviso de obra e ia fazer à mão do mesmo jeito. Atalho
# que não age não economiza os 5 minutos que motivaram tudo — só adiciona um
# passo.
#
# Duas regras aqui valem dinheiro:
#
# - **Só o pedido daquela conversa, daquela loja.** Agir no pedido errado é
#   pior que não agir: cancelar a venda de outro cliente é irreversível.
# - **Destrutivo exige `confirmado=True`.** Sem isso, erro de digitação vira
#   venda perdida. Quem confirma é a tela; aqui só se recusa.

import logging

logger = logging.getLogger(__name__)


@dataclass
class Resultado:
    ok: bool
    texto: str
    #: Só `/pix` fala com a cliente, e de propósito. O resto é para a dona ler.
    enviar_ao_cliente: bool = False


def _pedido_da_conversa(conversa, store):
    """O pedido aberto DAQUELA conversa, DAQUELA loja. Nunca outro."""
    from apps.stores.models import StoreOrder

    telefone = (getattr(conversa, 'phone_number', '') or '').strip()
    if not telefone or store is None:
        return None

    from apps.users.signals import _phone_candidates

    return (
        StoreOrder.objects
        .filter(store=store, customer_phone__in=_phone_candidates(telefone))
        .exclude(status__in=['delivered', 'cancelled'])
        .order_by('-created_at')
        .first()
    )


def _mudar_bot(conversa, ligado: bool):
    """Liga/desliga o bot nesta conversa.

    O estado canônico é `ConversationHandover.status` — o mesmo que o botão de
    assumir/devolver do inbox usa. Guardar isto em outro lugar criaria duas
    verdades sobre quem está falando com o cliente, que é exatamente o defeito
    que produziu MESSAGE DROPPED no bypass do modo humano.
    """
    from apps.handover.models import ConversationHandover, HandoverStatus

    ConversationHandover.objects.update_or_create(
        conversation=conversa,
        defaults={'status': HandoverStatus.BOT if ligado else HandoverStatus.HUMAN},
    )


def executar(nome: str, argumento: str = '', *, conversa=None, store=None,
             confirmado: bool = False) -> Resultado:
    """Executa um atalho. Nunca levanta — devolve `Resultado(ok=False)`."""
    meta = COMANDOS.get(nome)
    if meta is None:
        return Resultado(False, f'Não conheço /{nome}.')

    if meta['confirmar'] and not confirmado:
        return Resultado(False, f'/{nome} precisa de confirmação.')

    try:
        return _executar(nome, argumento, conversa, store, confirmado)
    except Exception as exc:
        logger.warning('[comandos] /%s falhou: %s', nome, exc)
        return Resultado(False, f'Não consegui executar /{nome} agora.')


def _executar(nome, argumento, conversa, store, confirmado) -> Resultado:
    if nome == 'bot':
        alvo = (argumento or '').strip().lower()
        if alvo not in ('on', 'off'):
            return Resultado(False, 'Use /bot on ou /bot off.')
        _mudar_bot(conversa, alvo == 'on')
        return Resultado(True, f'Bot {"ligado" if alvo == "on" else "desligado"} nesta conversa.')

    pedido = _pedido_da_conversa(conversa, store)
    if pedido is None:
        return Resultado(False, 'Não encontrei nenhum pedido aberto desta cliente.')

    if nome == 'pedido':
        return Resultado(True, _resumo_do_pedido(pedido))

    if nome == 'status':
        from apps.stores.models import StoreOrder

        rotulo = dict(StoreOrder.OrderStatus.choices).get(pedido.status, pedido.status)
        return Resultado(True, f'Pedido {pedido.order_number}: *{rotulo}*')

    if nome == 'nota':
        recado = (argumento or '').strip()
        if not recado:
            return Resultado(False, 'Escreva o recado: /nota o que anotar')
        metadata = pedido.metadata if isinstance(pedido.metadata, dict) else {}
        notas = list(metadata.get('notas_internas') or [])
        notas.append(recado)
        metadata['notas_internas'] = notas
        type(pedido).objects.filter(id=pedido.id).update(metadata=metadata)
        return Resultado(True, f'Anotado (só você vê): {recado}')

    if nome == 'entregue':
        from apps.stores.models import StoreOrder

        pedido.status = StoreOrder.OrderStatus.DELIVERED
        pedido.save(update_fields=['status', 'updated_at'])
        return Resultado(True, f'Pedido {pedido.order_number} marcado como entregue.')

    if nome == 'cancelar':
        from apps.stores.models import StoreOrder

        pedido.status = StoreOrder.OrderStatus.CANCELLED
        pedido.save(update_fields=['status', 'updated_at'])
        return Resultado(True, f'Pedido {pedido.order_number} cancelado.')

    if nome == 'cupom':
        codigo = (argumento or '').strip().upper()
        if not codigo:
            return Resultado(False, 'Informe o cupom: /cupom CODIGO')
        return _aplicar_cupom(pedido, codigo)

    if nome == 'pix':
        return _gerar_pix(pedido)

    return Resultado(False, f'/{nome} ainda não faz nada.')


def _resumo_do_pedido(pedido) -> str:
    linhas = [f'*{pedido.order_number}* — R$ {pedido.total}']
    for item in pedido.items.all()[:15]:
        linhas.append(f'• {item.quantity}x {item.product_name}')
    return '\n'.join(linhas)


def _aplicar_cupom(pedido, codigo: str) -> Resultado:
    from apps.stores.models import StoreCoupon

    cupom = StoreCoupon.objects.filter(
        store=pedido.store, code__iexact=codigo, is_active=True,
    ).first()
    if cupom is None:
        return Resultado(False, f'Cupom {codigo} não existe ou está inativo.')

    pedido.coupon = cupom
    pedido.save(update_fields=['coupon', 'updated_at'])

    from apps.stores.services.checkout_service import CheckoutService

    if hasattr(CheckoutService, 'recalculate_totals'):
        CheckoutService.recalculate_totals(pedido)
        pedido.refresh_from_db()

    return Resultado(True, f'Cupom {codigo} aplicado. Novo total: R$ {pedido.total}')


def _gerar_pix(pedido) -> Resultado:
    """O único comando que fala com a cliente — é o ponto dele."""
    from apps.stores.services.checkout_service import CheckoutService

    resultado = CheckoutService.create_payment(pedido, payment_method='pix')
    codigo = (resultado or {}).get('pix_code') or getattr(pedido, 'pix_code', '')
    if not codigo:
        return Resultado(False, 'Não consegui gerar o PIX agora.')

    return Resultado(
        True,
        f'PIX de R$ {pedido.total}:\n\n{codigo}',
        enviar_ao_cliente=True,
    )
