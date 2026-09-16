"""Registrar dinheiro recebido FORA do sistema: espécie, maquininha, PIX direto.

Por que uma cobrança (`StorePayment`) e não só o rótulo, como o "Pagamento
lançado" faz: o registro tem VALOR. Pedido de R$ 100 com R$ 30 de PIX e R$ 70
em dinheiro só fecha se os R$ 70 existirem em algum lugar — e o lugar das
cobranças é `StorePayment` (`amount_paid` já é derivado dele).

Isto NÃO cria segundo livro-caixa:
- a receita continua lendo `payment_status` (metrics/definicoes.py);
- o relatório de pagamentos (`analytics_views`) soma cobranças dos pedidos de
  receita e soma à parte só os pedidos SEM cobrança — um pedido nunca está nos
  dois lados.

O rótulo segue a MESMA trava do webhook (`_handle_storepayment_webhook`): só
vira `paid` quando o recebido cobre o total. Diferença deliberada: pedido que
já estava `paid` nunca é rebaixado — já está no faturamento por decisão do dono.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.stores.models import StoreOrder, StorePayment

# Slugs canônicos (os mesmos de StorePayment.PaymentMethod). `card` e `link`
# são dialetos provisórios e ficam de fora de propósito.
METODOS_MANUAIS = ('cash', 'debit_card', 'credit_card', 'pix', 'voucher', 'other')

# Métodos que descrevem o pedido inteiro quando pagam tudo sozinhos. `other`
# não diz nada — o pedido mantém o que tinha.
_METODOS_QUE_NOMEIAM_O_PEDIDO = set(METODOS_MANUAIS) - {'other'}

_STATUS_SEM_COBRANCA = {
    StoreOrder.OrderStatus.CANCELLED,
    StoreOrder.OrderStatus.REFUNDED,
    StoreOrder.OrderStatus.FAILED,
}


class RegistroRecusado(Exception):
    def __init__(self, code: str, mensagem: str):
        super().__init__(mensagem)
        self.code = code
        self.mensagem = mensagem


@dataclass
class ResultadoDoRegistro:
    pedido: StoreOrder
    cobranca: StorePayment
    criado: bool
    quitou: bool


def _ler_valor(bruto):
    if bruto is None or bruto == '':
        return None
    try:
        valor = Decimal(str(bruto).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise RegistroRecusado('valor_invalido', 'Informe um valor válido.')
    if not valor.is_finite() or valor <= 0:
        raise RegistroRecusado('valor_invalido', 'O valor precisa ser maior que zero.')
    return valor


def _saldo(pedido_id):
    """Pedido recarregado com `amount_paid` fresco (sem annotation velha)."""
    return StoreOrder.objects.get(pk=pedido_id)


def registrar_pagamento(pedido_id, usuario, metodo, valor=None, chave_idempotencia='', observacao=''):
    if metodo not in METODOS_MANUAIS:
        raise RegistroRecusado(
            'metodo_invalido',
            f'Forma de pagamento inválida. Use uma de: {", ".join(METODOS_MANUAIS)}.',
        )
    valor = _ler_valor(valor)
    chave = (chave_idempotencia or '').strip()[:100]

    with transaction.atomic():
        # A linha travada serializa o duplo clique: o segundo pedido só lê o
        # saldo depois que o primeiro gravou.
        pedido = StoreOrder.objects.select_for_update().get(pk=pedido_id)

        if chave:
            existente = StorePayment.objects.filter(
                order_id=pedido.pk, metadata__registro_manual__chave=chave,
            ).first()
            if existente:
                return ResultadoDoRegistro(_saldo(pedido.pk), existente, criado=False,
                                           quitou=_saldo(pedido.pk).is_fully_paid)

        if pedido.status in _STATUS_SEM_COBRANCA:
            raise RegistroRecusado('pedido_encerrado', 'Pedido cancelado não recebe pagamento.')

        falta = pedido.amount_due
        if falta <= 0:
            raise RegistroRecusado('ja_quitado', 'Este pedido já está pago.')
        if valor is None:
            valor = falta
        if valor > falta:
            raise RegistroRecusado(
                'valor_acima_do_saldo',
                f'Falta receber R$ {falta:.2f}'.replace('.', ',')
                + ' — registre no máximo esse valor (troco não entra).',
            )

        estava_pago = pedido.payment_status == StoreOrder.PaymentStatus.PAID
        paid_at_antes = pedido.paid_at
        cobrancas_anteriores = pedido.payments.filter(
            status=StorePayment.PaymentStatus.COMPLETED).exists()
        agora = timezone.now()

        cobranca = StorePayment(
            order=pedido, store_id=pedido.store_id, gateway=None,
            status=StorePayment.PaymentStatus.COMPLETED,
            payment_method=metodo, amount=valor, fee=Decimal('0'), net_amount=valor,
            paid_at=agora, payer_name=(pedido.customer_name or '')[:255],
            metadata={'registro_manual': {
                'user_id': str(usuario.id) if usuario and usuario.is_authenticated else '',
                'usuario': getattr(usuario, 'username', '') or '',
                'registrado_em': agora.isoformat(),
                'observacao': (observacao or '').strip()[:500],
                'chave': chave,
            }},
        )
        # save() dispara `_sync_with_order`, que marca `paid` já na primeira
        # cobrança quitada. O ajuste abaixo reaplica a trava de parcial.
        cobranca.save()

        pedido = _saldo(pedido.pk)
        quitou = pedido.amount_paid >= (pedido.total or Decimal('0'))
        campos = set()

        if quitou:
            if pedido.payment_status != StoreOrder.PaymentStatus.PAID:
                pedido.payment_status = StoreOrder.PaymentStatus.PAID
                campos.add('payment_status')
            if paid_at_antes and pedido.paid_at != paid_at_antes:
                pedido.paid_at = paid_at_antes
                campos.add('paid_at')
            # A gaveta conta `payment_method='cash'` do PEDIDO. Pagou tudo num
            # método só, é esse o método do pedido.
            if not cobrancas_anteriores and metodo in _METODOS_QUE_NOMEIAM_O_PEDIDO \
                    and pedido.payment_method != metodo:
                pedido.payment_method = metodo
                campos.add('payment_method')
        elif estava_pago:
            # Já estava no faturamento: a cobrança soma, o rótulo fica.
            if pedido.payment_status != StoreOrder.PaymentStatus.PAID or pedido.paid_at != paid_at_antes:
                pedido.payment_status = StoreOrder.PaymentStatus.PAID
                pedido.paid_at = paid_at_antes
                campos.update({'payment_status', 'paid_at'})
        else:
            pedido.payment_status = StoreOrder.PaymentStatus.PROCESSING
            pedido.paid_at = paid_at_antes
            campos.update({'payment_status', 'paid_at'})

        if campos:
            campos.add('updated_at')
            pedido.save(update_fields=sorted(campos))
            pedido = _saldo(pedido.pk)

    return ResultadoDoRegistro(pedido, cobranca, criado=True, quitou=quitou)
