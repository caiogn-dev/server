"""Checkout de convidado não pode morrer quando a conta já tem carrinho ativo.

Incidente 06/ago: todo POST /checkout/ da Cê Saladas devolvia 400
"Erro ao processar checkout". Log real:

    Checkout error: duplicate key value violates unique constraint
    "unique_active_cart_per_user_store"
    DETAIL: Key (user_id, store_id)=(15, d534b720-...) already exists.

Causa: o cliente fechava como convidado (carrinho de sessão, user=None), mas
`_create_order_atomic` resolvia `customer_user` pelo e-mail/telefone e
reivindicava o carrinho (`cart.user = customer_user`). Se aquela conta já
tinha um carrinho ativo abandonado, a constraint parcial estourava e o
`except Exception` genérico da view transformava tudo em 400.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCategory,
    StoreProduct,
)
from apps.core.models import UserProfile
from apps.stores.services.cart_service import CartService
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class GuestCheckoutClaimsCartTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-cartclaim', password='x', email='dono-cartclaim@real.com',
        )
        self.store = Store.objects.create(
            name='Loja CartClaim', slug='loja-cartclaim',
            owner=self.owner, status='active',
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Saladas', slug='saladas',
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Especial',
            slug='especial', price=Decimal('39.99'), is_active=True,
            track_stock=False,
        )
        # Conta existente do cliente, com carrinho ativo abandonado.
        # O telefone tem prioridade na resolução de identidade (auth por
        # WhatsApp), então o perfil precisa carregá-lo para reproduzir o caso.
        self.cliente = User.objects.create_user(
            username='cliente-cartclaim', password='x',
            email='cliente-cartclaim@real.com',
        )
        perfil, _ = UserProfile.objects.get_or_create(user=self.cliente)
        perfil.phone = '5563988771122'
        perfil.save(update_fields=['phone'])
        self.carrinho_orfao = StoreCart.objects.create(
            store=self.store, user=self.cliente, is_active=True,
        )

    def test_convidado_finaliza_mesmo_com_carrinho_orfao_da_conta(self):
        carrinho_convidado = CartService.get_or_create_cart(
            self.store, None, 'cart_regressao_400',
        )
        CartService.add_product(carrinho_convidado, self.product, 1)

        pedido = CheckoutService.create_order(
            cart=carrinho_convidado,
            customer_data={
                'name': 'Cliente',
                'email': 'cliente-cartclaim@real.com',
                'phone': '63988771122',
            },
            delivery_data={'method': 'pickup'},
        )

        self.assertIsNotNone(pedido)
        self.carrinho_orfao.refresh_from_db()
        self.assertFalse(
            self.carrinho_orfao.is_active,
            'carrinho órfão da conta deve ser desativado ao reivindicar o do convidado',
        )
