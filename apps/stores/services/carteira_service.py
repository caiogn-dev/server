"""Carteira pré-paga: o cliente compra saldo adiantado e ganha bônus.

POR QUE ISTO EXISTE, EM NÚMEROS DA CÊ SALADAS (12 semanas, 129 pedidos):
81 clientes únicos, e 57 deles compraram UMA vez e nunca voltaram. Os 13 que
voltaram três ou mais vezes são 45% do faturamento. O problema da loja não é
ticket, é segunda compra — e saldo comprado adiantado é a única mecânica que
resolve isso sem descontar a comida, porque enquanto houver saldo o cliente
não pede em outro lugar.

TRÊS DECISÕES QUE MOLDAM ESTE ARQUIVO:

1. **A chave é o TELEFONE.** O saldo mora em `StoreCashbackLot`, que já é por
   telefone justamente porque o checkout do storefront é guest-first. Exigir
   login para usar a carteira mataria o produto no cadastro.

2. **A cobrança vira VENDA.** Sem o pedido, os R$ 270 somem do relatório: os
   pedidos seguintes saem com desconto e faturamento nenhum, e o mês fecha
   como se a loja não tivesse vendido. O pedido nasce `digital` e com
   `source='carteira'` porque o BI agrupa por `source` — foi mislabelar isso
   que fez a tela de canais mentir em 15/ago.

3. **O crédito é IDEMPOTENTE por cobrança**, garantido por constraint
   (`cashback_unico_por_cobranca`). O Mercado Pago reentrega webhook; sem a
   trava de banco, cada reentrega dá um pacote de graça.
"""
import logging
import uuid
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIXO = 'carteira'


def _ref(tier_id: str, telefone: str) -> str:
    """`carteira:<pacote>:<telefone>:<nonce>`.

    O nonce é obrigatório: sem ele, o mesmo cliente comprando o mesmo pacote
    duas vezes no mês geraria a mesma referência, e a constraint de
    idempotência recusaria a SEGUNDA COMPRA LEGÍTIMA — o cliente pagaria e não
    receberia saldo.
    """
    return f'{PREFIXO}:{tier_id}:{telefone}:{uuid.uuid4().hex[:12]}'


def decompor(external_reference: str):
    """Devolve (tier_id, telefone) de uma referência de carteira, ou None."""
    partes = str(external_reference or '').split(':')
    if len(partes) < 4 or partes[0] != PREFIXO:
        return None
    return partes[1], partes[2]


def e_de_carteira(external_reference: str) -> bool:
    return str(external_reference or '').startswith(f'{PREFIXO}:')


class CarteiraService:

    @staticmethod
    def pacotes(store) -> list:
        from apps.stores.services.cashback_service import CashbackService
        return CashbackService.tiers(store)

    @staticmethod
    def saldo(store, phone: str) -> dict:
        """O que a vitrine mostra: quanto tem e quando some.

        `expira_em` não é enfeite — saldo sem data visível é saldo que o
        cliente descobre ter perdido, e isso não gera recompra, gera briga.
        """
        from apps.stores.services.cashback_service import CashbackService
        vence = CashbackService.expires_next(store, phone)
        return {
            'saldo': str(CashbackService.balance(store, phone)),
            'expira_em': vence.isoformat() if vence else None,
        }

    @staticmethod
    def comprar(store, phone: str, tier_id: str, payer_name: str = '',
                payer_email: str = '', payment_payload: dict = None) -> dict:
        """Gera a cobrança PIX de um pacote. O saldo só entra quando ela é paga.

        Creditar aqui, na intenção de compra, seria dar saldo a quem abriu a
        tela e nunca pagou.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.services.cashback_service import CashbackService
        from apps.stores.services.checkout_service import CheckoutService

        telefone = normalize_phone_number(phone or '')
        if not telefone:
            raise ValueError('Informe um celular válido para receber o saldo.')

        pacote = CashbackService.tier(store, tier_id)
        if pacote is None:
            raise ValueError('Pacote indisponível.')
        if not CashbackService.is_enabled(store):
            raise ValueError('A carteira não está ativa nesta loja.')

        payload = dict(payment_payload or {})
        payload['external_reference'] = _ref(pacote['id'], telefone)
        payload['payer_name'] = payer_name or 'Cliente'
        if payer_email:
            payload['payer_email'] = payer_email

        resultado = CheckoutService.create_payment(
            order=None,
            payment_method='pix',
            payment_data=payload,
            amount=pacote['paga'],
            store=store,
            description=f'Carteira {store.name} · Pacote {pacote["nome"]}',
        )
        resultado['pacote'] = {
            'id': pacote['id'], 'nome': pacote['nome'],
            'paga': str(pacote['paga']), 'credito': str(pacote['credito']),
            'bonus': str(pacote['bonus']),
        }
        return resultado

    @staticmethod
    def aplicar_pagamento(store_payment):
        """Cobrança de pacote foi paga: credita o saldo e registra a venda.

        Nesta ordem de propósito. Se a criação do pedido falhar, o cliente já
        tem o saldo que pagou — um relatório furado se conserta depois, um
        cliente sem o saldo que comprou vira reembolso e desconfiança.
        """
        from apps.stores.services.cashback_service import CashbackService

        partes = decompor(store_payment.external_reference)
        if partes is None:
            logger.warning(
                'carteira: cobrança %s sem referência decifrável (%r)',
                store_payment.id, store_payment.external_reference,
            )
            return None
        tier_id, telefone = partes
        store = store_payment.store

        lote = CashbackService.credit_prepaid(
            store, telefone, tier_id=tier_id,
            source_ref=str(store_payment.external_reference),
        )
        if lote is None:
            # Já creditado (webhook reentregue) ou pacote saiu do catálogo.
            # Nos dois casos não se credita de novo nem se duplica a venda.
            logger.info('carteira: cobrança %s não gerou crédito novo', store_payment.id)
            return store_payment.order

        return CarteiraService._venda_do_pacote(store_payment, tier_id, lote)

    @staticmethod
    def _venda_do_pacote(store_payment, tier_id: str, lote):
        """A venda do pacote no relatório.

        O valor da venda é o que ENTROU (`store_payment.amount`, R$ 270), nunca
        o crédito concedido (R$ 304): faturamento é dinheiro recebido. O bônus
        aparece sozinho depois, como desconto nos pedidos que gastarem o saldo.
        """
        from apps.stores.models import StoreOrder, StoreOrderItem
        from apps.stores.services.cashback_service import CashbackService

        store_payment.refresh_from_db()
        if store_payment.order_id:
            return store_payment.order

        pacote = CashbackService.tier(store_payment.store, tier_id) or {}
        nome = pacote.get('nome') or tier_id

        order = StoreOrder.objects.create(
            store=store_payment.store,
            total=store_payment.amount,
            subtotal=store_payment.amount,
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PAID,
            payment_method=store_payment.payment_method or 'pix',
            paid_at=store_payment.paid_at or timezone.now(),
            customer_name=store_payment.payer_name or 'Cliente',
            customer_phone=lote.phone,
            # 'digital': não tem comida para preparar nem endereço para ir.
            # A comanda precisa dizer isso, senão a cozinha monta uma salada
            # que ninguém pediu.
            delivery_method=StoreOrder.DeliveryMethod.DIGITAL,
            # O BI agrupa por `source`. Deixar cair em 'web' creditaria o
            # cardápio por uma venda que não passou por ele.
            source='carteira',
            metadata={
                'origem': 'carteira_prepaga',
                'pacote': tier_id,
                'credito_concedido': str(lote.amount),
                'store_payment_id': str(store_payment.id),
            },
        )
        StoreOrderItem.objects.create(
            order=order,
            # `product` nulo de propósito: inventar um item de cardápio sujaria
            # estoque e ranking de mais vendidos com algo que não é comida.
            product=None,
            product_name=f'Carteira · Pacote {nome} (saldo de R$ {lote.amount})',
            unit_price=store_payment.amount,
            quantity=1,
            subtotal=store_payment.amount,
        )
        store_payment.order = order
        store_payment.save(update_fields=['order', 'updated_at'])
        logger.info(
            'carteira: pacote %s creditado para %s (R$ %s) — pedido %s',
            tier_id, lote.phone, lote.amount, order.order_number,
        )
        return order
