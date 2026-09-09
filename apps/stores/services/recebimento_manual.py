"""Dar baixa num pagamento: registrar o DINHEIRO, não só o rótulo.

O painel marca "Pagamento lançado" e o pedido ganhava `payment_status='paid'`.
Só que o saldo do pedido é DERIVADO das cobranças — `StoreOrder.amount_paid`
soma os `StorePayment` com status `completed`, e não existe campo físico. Sem
criar a cobrança, o pedido ficava com duas verdades em desacordo: o rótulo
dizia pago, o saldo dizia que faltava tudo.

Medido na Cê Saladas em 09/09/2026: de 52 pedidos já entregues com
`amount_due > 0`, **51 tinham `payment_status = 'paid'`**. O modal anunciava
"Falta receber R$ 41,32" num pedido entregue e quitado, e o relatório de
receita contava menos do que a loja faturou.

Dois endpoints do painel marcam pago (o `PATCH` do quadro e o
`update_payment_status/`). Por isso isto é uma função de serviço e não um
trecho dentro de uma view: se só um dos caminhos registrasse o dinheiro, o
defeito voltaria pelo outro.
"""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def registrar_recebimento(order, autor=None, metodo: str = '') -> object | None:
    """Cria a cobrança que falta para o pedido ficar quitado.

    Devolve o `StorePayment` criado, ou `None` quando não havia o que
    registrar (pedido já quitado, ou sem total).

    IDEMPOTENTE POR CONSTRUÇÃO: registra exatamente `amount_due`, então
    chamar duas vezes não cria a segunda cobrança — na segunda o saldo já é
    zero. É o que impede o clique dobrado de contar a venda duas vezes.

    Também respeita pagamento PARCIAL: um pedido com R$ 20 de PIX recebido e
    R$ 21,32 em dinheiro registra só a diferença, e o relatório continua
    sabendo quanto entrou por cada forma.
    """
    from apps.stores.models import StorePayment

    # `amount_due` já é `max(0, total - recebido)`, então isto cobre o pedido
    # quitado e o valor negativo por ajuste manual.
    falta = order.amount_due
    if falta <= Decimal('0.00'):
        return None

    cobranca = StorePayment.objects.create(
        order=order,
        # A forma é a do PEDIDO: quem recebeu em dinheiro não pode virar
        # "pix" no relatório de formas de pagamento.
        payment_method=metodo or order.payment_method or 'cash',
        status='completed',
        amount=falta,
        metadata={
            'origem': 'baixa_manual',
            'autor': str(getattr(autor, 'id', '') or ''),
        },
    )
    # A annotation `amount_paid_agg` do queryset da view é uma FOTOGRAFIA
    # tirada no fetch, e a property `amount_paid` PREFERE a annotation.
    # Sem invalidá-la, quem chamou continua lendo o saldo velho — e a
    # resposta do PATCH voltava dizendo "Falta receber" logo depois de
    # registrar o recebimento.
    if hasattr(order, 'amount_paid_agg'):
        del order.amount_paid_agg

    logger.info(
        'Baixa manual registrada: pedido %s, %s via %s',
        order.order_number, falta, cobranca.payment_method,
    )
    return cobranca
