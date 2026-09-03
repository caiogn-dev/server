"""Cupom recusado no checkout NÃO pode virar pedido com preço cheio.

O caso real (Leani, 03/09, CE-2609038526): a sacola aprovou BEMVINDO10, a tela
mostrou o desconto, e no checkout a regra `first_order_only` disparou — ela já
tinha um pedido entregue no dia anterior. O código de então apenas anotava
`metadata.coupon_rejected` e seguia: o pedido saiu por R$ 43,28 em vez de
R$ 38,95, sem uma palavra para a cliente nem para a loja.

Ela pagou R$ 38,95 num segundo PIX; como o pedido valia R$ 43,28, o backend leu
pagamento PARCIAL e travou a venda em `processing` para sempre.

A regra agora: se o cliente pediu um desconto e ele não vale, o checkout PARA e
diz o motivo. Cobrar mais do que a tela prometeu é o único desfecho inaceitável
— o cliente tira o cupom e confirma, ou a loja corrige a regra.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreCoupon, StoreProduct,
)
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()

TELEFONE = '5563992618115'


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_recusa', password='x')
    return Store.objects.create(owner=dono, name='Loja Recusa', slug='loja-recusa-test')


@pytest.fixture
def produto(loja):
    cat = StoreCategory.objects.create(store=loja, name='Saladas', slug='saladas')
    return StoreProduct.objects.create(
        store=loja, category=cat, name='Especial Filé de Frango',
        slug='especial-file', price=Decimal('32.99'),
        status='active', track_stock=False,
    )


@pytest.fixture
def carrinho(loja, produto):
    cart = StoreCart.objects.create(store=loja, session_key='sess-recusa')
    StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)
    return cart


def _cupom_primeira_compra(loja):
    return StoreCoupon.objects.create(
        store=loja, code='BEMVINDO10',
        discount_type='percentage', discount_value=Decimal('10'),
        first_order_only=True, is_active=True,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )


def _cliente():
    return {'name': 'Leani Rodrigues', 'email': '', 'phone': TELEFONE, 'cpf': ''}


def _entrega():
    return {'method': 'pickup', 'address': {}}


@pytest.mark.django_db
class TestCupomRecusadoNaoSaiCalado:

    def test_cupom_invalido_derruba_o_checkout_com_o_motivo(self, loja, produto, carrinho):
        """Cupom que não vale = checkout para, com o motivo em português."""
        _cupom_primeira_compra(loja)

        # Primeira compra: passa e queima o direito ao cupom.
        primeiro = CheckoutService.create_order(
            cart=carrinho, customer_data=_cliente(), delivery_data=_entrega(),
            coupon_code='BEMVINDO10',
        )
        primeiro.payment_status = 'paid'
        primeiro.status = 'delivered'
        primeiro.save(update_fields=['payment_status', 'status'])
        assert primeiro.discount > 0, 'a primeira compra tinha direito ao desconto'

        # Segunda compra com o mesmo cupom: agora a regra recusa.
        carrinho2 = StoreCart.objects.create(store=loja, session_key='sess-recusa-2')
        StoreCartItem.objects.create(
            cart=carrinho2, product=produto, quantity=1,
        )

        with pytest.raises(ValueError) as erro:
            CheckoutService.create_order(
                cart=carrinho2, customer_data=_cliente(), delivery_data=_entrega(),
                coupon_code='BEMVINDO10',
            )

        mensagem = str(erro.value)
        assert 'BEMVINDO10' in mensagem
        assert 'primeira compra' in mensagem.lower()

    def test_nenhum_pedido_e_criado_quando_o_cupom_cai(self, loja, produto, carrinho):
        """O buraco que custou dinheiro: pedido cheio criado do mesmo jeito."""
        from apps.stores.models import StoreOrder
        _cupom_primeira_compra(loja)

        primeiro = CheckoutService.create_order(
            cart=carrinho, customer_data=_cliente(), delivery_data=_entrega(),
            coupon_code='BEMVINDO10',
        )
        primeiro.payment_status = 'paid'
        primeiro.status = 'delivered'
        primeiro.save(update_fields=['payment_status', 'status'])

        carrinho2 = StoreCart.objects.create(store=loja, session_key='sess-recusa-3')
        StoreCartItem.objects.create(
            cart=carrinho2, product=produto, quantity=1,
        )
        antes = StoreOrder.objects.filter(store=loja).count()

        with pytest.raises(ValueError):
            CheckoutService.create_order(
                cart=carrinho2, customer_data=_cliente(), delivery_data=_entrega(),
                coupon_code='BEMVINDO10',
            )

        assert StoreOrder.objects.filter(store=loja).count() == antes, (
            'checkout recusado não pode deixar pedido cobrando o preço cheio'
        )

    def test_sem_cupom_o_checkout_segue_normal(self, loja, carrinho):
        """Guarda: a trava só vale para quem pediu desconto."""
        pedido = CheckoutService.create_order(
            cart=carrinho, customer_data=_cliente(), delivery_data=_entrega(),
        )
        assert pedido.discount == Decimal('0.00')
        assert pedido.total > 0
