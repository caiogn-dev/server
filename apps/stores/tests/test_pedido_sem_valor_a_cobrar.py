"""Pedido que não deve nada não pode passar pela cobrança.

19/10, Cê Saladas — Wanny (CE-2610192528): um Salmão Sublime (R$ 52,90) para
RETIRADA, pago inteiro pelo resgate do cartão fidelidade. Total R$ 0,00.
A tela de pagamento pediu uma forma de pagamento (ela não sabia o que
escolher), ela marcou PIX, e o checkout tentou gerar um PIX de R$ 0,00:
`create_payment` levantou "Valor da cobranca deve ser maior que zero", o
pedido nasceu `payment_status=failed` e ela viu erro num pedido que estava
certo.

A regra: total zero = nada a cobrar. O pedido nasce PAGO (sem cobrança) e
CONFIRMADO, como o pago no cartão, e nenhuma cobrança é tentada — venha o
método que vier (a tela antiga em cache ainda manda 'pix'). Com qualquer valor
a pagar (outro produto, entrega cobrada) nada muda.

E a salada grátis não rende carimbo: só as pagas contam (dono, 19/10). Até
aqui `order_qualified_units` contava o item resgatado — CE-2610028836 pagou só
a entrega e ganhou 1 carimbo.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store, StoreCartItem, StoreCategory, StoreLoyaltyAccount, StoreOrder, StoreProduct,
)
from apps.stores.services import cart_service
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


class PedidoSemValorACobrarTests(APITestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-zero', password='x', email='dono-zero@real.com')
        self.cliente = User.objects.create_user(
            username='wanny-zero', password='x', email='wanny.zero@real.com',
        )
        self.loja = Store.objects.create(
            owner=dono, name='Cê', slug='ce-zero',
            store_type=Store.StoreType.FOOD, status=Store.StoreStatus.ACTIVE, currency='BRL',
        )
        saladas = StoreCategory.objects.create(store=self.loja, name='Saladas', slug='saladas')
        bebidas = StoreCategory.objects.create(store=self.loja, name='Bebidas', slug='bebidas')
        self.loja.metadata = {
            'loyalty_enabled': True,
            'loyalty_salads_required': 10,
            'loyalty_qualifying_categories': [str(saladas.id)],
        }
        self.loja.save(update_fields=['metadata'])
        self.salmao = StoreProduct.objects.create(
            store=self.loja, category=saladas, name='Salmão Sublime', slug='salmao',
            price=Decimal('52.90'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.suco = StoreProduct.objects.create(
            store=self.loja, category=bebidas, name='Suco', slug='suco',
            price=Decimal('12.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        StoreLoyaltyAccount.objects.create(store=self.loja, user=self.cliente, qualified_count=10)
        self.carrinho = cart_service.get_or_create_cart(self.loja, user=self.cliente, session_key=None)
        self.client.force_authenticate(self.cliente)

    def _checkout(self, payment_method='pix'):
        payload = {
            'customer_name': 'Wanny Tapajos',
            'customer_email': self.cliente.email,
            'customer_phone': '+5563999990002',
            'delivery_method': 'pickup',
            'use_loyalty_reward': True,
        }
        if payment_method:
            payload['payment_method'] = payment_method
        with patch('apps.stores.services.print_service.enqueue_order_print_job'), \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'), \
                patch(
                    'apps.stores.api.views.storefront_views.checkout_service.create_payment',
                    return_value={'success': True, 'status': 'pending', 'payment_id': 'pix-1'},
                ) as cobranca:
            resp = self.client.post(
                f'/api/v1/stores/{self.loja.slug}/checkout/', payload, format='json',
            )
        return resp, cobranca

    def _so_a_salada_gratis(self):
        StoreCartItem.objects.create(cart=self.carrinho, product=self.salmao, quantity=1)

    # ── o caso da Wanny ───────────────────────────────────────────────────

    def test_so_a_salada_gratis_com_pix_nao_tenta_cobrar(self):
        self._so_a_salada_gratis()
        resp, cobranca = self._checkout('pix')

        self.assertEqual(resp.status_code, 201, resp.data)
        cobranca.assert_not_called()
        self.assertFalse(resp.data.get('payment_error'))

    def test_pedido_zerado_nasce_pago_e_confirmado(self):
        self._so_a_salada_gratis()
        resp, _ = self._checkout('pix')

        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertEqual(pedido.total, Decimal('0.00'))
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(pedido.payment_method, 'sem_cobranca')
        self.assertEqual(pedido.status, StoreOrder.OrderStatus.CONFIRMED)
        self.assertIsNotNone(pedido.paid_at)

    def test_resposta_leva_a_tela_ao_sucesso(self):
        """O site em cache lê `payment.status == 'approved'` → tela de sucesso."""
        self._so_a_salada_gratis()
        resp, _ = self._checkout('pix')

        self.assertEqual(resp.data['payment']['status'], 'approved')
        self.assertEqual(resp.data['payment']['payment_method'], 'sem_cobranca')

    def test_pedido_zerado_nao_conta_como_compra_na_meta(self):
        """Compra de R$ 0,00 inflaria as conversões dos anúncios."""
        self._so_a_salada_gratis()
        # O envio mora num on_commit: sem executar os callbacks o teste
        # passaria mesmo sem a trava.
        with patch('apps.stores.tasks.send_meta_purchase_event') as meta, \
                self.captureOnCommitCallbacks(execute=True):
            self._checkout('pix')
        meta.delay.assert_not_called()

    def test_tela_nova_nao_manda_metodo_e_tambem_passa(self):
        self._so_a_salada_gratis()
        resp, cobranca = self._checkout(payment_method=None)

        self.assertEqual(resp.status_code, 201, resp.data)
        cobranca.assert_not_called()
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)

    # ── com algo a pagar, nada muda ──────────────────────────────────────

    def test_com_outro_produto_a_cobranca_segue_normal(self):
        self._so_a_salada_gratis()
        StoreCartItem.objects.create(cart=self.carrinho, product=self.suco, quantity=1)
        resp, cobranca = self._checkout('pix')

        self.assertEqual(resp.status_code, 201, resp.data)
        cobranca.assert_called_once()
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertEqual(pedido.total, Decimal('12.00'))
        self.assertNotEqual(pedido.payment_method, 'sem_cobranca')

    # ── carimbo: só as pagas contam ──────────────────────────────────────

    def test_salada_gratis_sozinha_nao_rende_carimbo(self):
        self._so_a_salada_gratis()
        resp, _ = self._checkout('pix')
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])

        self.assertEqual(LoyaltyService.order_qualified_units(self.loja, pedido), 0)

    def test_resgate_mais_uma_paga_rende_um_carimbo(self):
        StoreCartItem.objects.create(cart=self.carrinho, product=self.salmao, quantity=2)
        resp, _ = self._checkout('pix')
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])

        self.assertEqual(LoyaltyService.order_qualified_units(self.loja, pedido), 1)

    def test_sem_resgate_conta_tudo_como_antes(self):
        StoreCartItem.objects.create(cart=self.carrinho, product=self.salmao, quantity=2)
        resp, _ = self._checkout('pix')
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        pedido.metadata = {**(pedido.metadata or {}), 'loyalty_reward': {'applied': False, 'count': 0}}
        pedido.save(update_fields=['metadata'])

        self.assertEqual(LoyaltyService.order_qualified_units(self.loja, pedido), 2)
