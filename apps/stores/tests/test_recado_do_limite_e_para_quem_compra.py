"""O recado do limite do plano está escrito para o DONO e chega a quem COMPRA.

Quando a loja do plano Grátis bate os 30 pedidos do mês, o checkout responde
400 com `detail: "Limite do plano atingido (30 pedidos/mês). Faça upgrade do
plano."` — e o storefront mostra isso na tela. Quem lê é a pessoa com a
sacola cheia, que não tem plano nenhum para fazer upgrade: ela descobre um
detalhe comercial da loja, não descobre o que fazer, e a venda morre ali.

Repare que o caminho gêmeo está CERTO: em `product_views.py` o mesmo texto vai
para o painel, onde quem lê é o dono e existe até um `PaywallModal` para
recebê-lo. O erro não é a mensagem — é o público.

O que este arquivo fixa:
  - quem compra lê um recado acionável e sem jargão de cobrança;
  - o motivo real continua legível por MÁQUINA (`code`), para o painel, o log
    e o suporte saberem que foi o limite do plano, e não a loja fechada.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreOrder,
    StoreProduct,
)

User = get_user_model()


@override_settings(REST_FRAMEWORK={
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
})
class RecadoDoLimiteTests(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(
            username='dono-limite-recado', password='x', email='d@limite.com',
        )
        self.store = Store.objects.create(
            name='Loja Limite', slug='loja-limite-recado', owner=owner,
            status='active', plan='free',
        )
        categoria = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-limite',
            is_active=True, sort_order=1,
        )
        produto = StoreProduct.objects.create(
            store=self.store, category=categoria, name='Prato',
            slug='prato-limite', price=Decimal('30.00'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        for i in range(30):
            StoreOrder.objects.create(
                store=self.store, order_number=f'limite-{i:04d}',
                customer_name='Histórico', customer_phone='63999990002',
                subtotal=Decimal('10.00'), total=Decimal('10.00'),
            )
        self.cart_key = 'cart-limite-recado'
        cart = StoreCart.objects.create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)

    def _checkout(self):
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            {
                'customer_name': 'Cliente Teste',
                'customer_email': 'cli@example.com',
                'customer_phone': '+5563999990001',
                'delivery_method': 'pickup',
                'payment_method': '',
            },
            format='json', HTTP_X_CART_KEY=self.cart_key,
        )

    def test_continua_barrando_a_venda(self):
        """A trava é do negócio e não muda: só o recado muda."""
        self.assertEqual(self._checkout().status_code, status.HTTP_400_BAD_REQUEST)

    def test_quem_compra_nao_e_mandado_fazer_upgrade_de_plano(self):
        recado = self._checkout().json().get('detail', '').lower()

        self.assertNotIn('upgrade', recado)
        self.assertNotIn('plano', recado)

    def test_o_recado_diz_o_que_fazer(self):
        """Erro que não oferece saída é beco sem saída."""
        recado = self._checkout().json().get('detail', '').lower()

        self.assertIn('loja', recado)

    def test_o_motivo_real_continua_legivel_por_maquina(self):
        """Painel, log e suporte precisam distinguir isto de 'loja fechada'."""
        self.assertEqual(self._checkout().json().get('code'), 'plan_order_limit')
