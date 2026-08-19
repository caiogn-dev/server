"""Checkout honesto quando o PIX falha.

Bug (incidente MP 06/jul): quando o Mercado Pago recusa a criação da cobrança
PIX, `create_payment` retornava `{'success': False}` sem tocar no pedido — ele
ficava `payment_status='pending'` como se existisse uma cobrança ativa, e o
checkout respondia 201 com `payment_status: 'pending'` no corpo. O caminho de
cartão já marca o pedido como FAILED; o de PIX não marcava nada.

11/ago/2026 — o contrato foi corrigido pela metade que faltava. Marcar
`order.status=FAILED` era honesto e destrutivo ao mesmo tempo: some com o
pedido da tela de quem está trabalhando. Foi o que aconteceu com o pedido da
Aline (CE-2608113992, R$ 270,37) pelo caminho do cartão — apareceu no painel e
sumiu um segundo depois, "como se tivesse sido excluído".

`payment_status=FAILED` já cumpre a honestidade inteira: ninguém finge
cobrança ativa. O `status` do pedido não é lugar de contar história de
pagamento — cobrança recusada é venda a recuperar (mandar PIX, cobrar na
entrega), não pedido morto.

Contrato honesto (sem quebrar os frontends, que já leem `payment_error` no
corpo 2xx — CheckoutPage.jsx:620 do cardapidex-web):
- service: PIX recusado marca payment_status=FAILED e NÃO mexe no status;
- service: cobrança avulsa (order=None) recusada não explode;
- view: mantém 201 (o pedido FOI criado) + `payment_error`, mas o corpo passa
  a dizer `payment_status='failed'` em vez de fingir cobrança pendente.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreOrder,
    StorePayment,
    StoreProduct,
)

User = get_user_model()


def _orders_rejeitando(message='invalid collector'):
    """Resposta de recusa da Orders API (o PIX nasce em /v1/orders desde 19/08)."""
    return (400, {'errors': [{'code': 'validation_error', 'message': message}]})


def _mp_sdk_rejeitando(message='invalid collector'):
    """SDK que também recusa a preference.

    Desde o fallback de 19/08, PIX recusado tenta o link de pagamento antes de
    desistir. Para o pedido terminar FAILED — que é o que estes testes
    garantem — as DUAS portas precisam estar fechadas. Com o link aberto o
    comportamento correto é outro e está coberto em test_pix_fallback_link.
    """
    sdk = MagicMock()
    sdk.preference().create.return_value = {
        'status': 400,
        'response': {'message': 'link indisponivel'},
    }
    return sdk


class CreatePaymentPixFailureTests(APITestCase):
    """Nível serviço: PIX recusado deve deixar o pedido em estado FAILED."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-pixfail', password='x', email='owner-pixfail@real.com',
        )
        self.store = Store.objects.create(
            name='Loja PixFail', slug='loja-pixfail', owner=self.owner, status='active',
        )

    def _order(self, total='50.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            customer_email='cli-pixfail@real.com',
            subtotal=Decimal(total), total=Decimal(total),
        )

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN', 'provider': 'mercadopago'})
    @patch('mercadopago.SDK')
    @patch('apps.stores.services.mp_orders.create_order',
           return_value=_orders_rejeitando('collector inválido'))
    def test_pix_recusado_marca_pedido_failed(self, _criar, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_sdk_rejeitando('collector inválido')
        order = self._order()

        result = CheckoutService.create_payment(order, 'pix')

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'collector inválido')
        # Nenhuma cobrança fantasma
        self.assertEqual(StorePayment.objects.filter(order=order).count(), 0)
        # Pedido honesto: pagamento FALHOU, sem fingir cobrança ativa...
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.FAILED)
        # ...e continua visível no painel: honestidade não é apagar a venda.
        self.assertNotEqual(order.status, StoreOrder.OrderStatus.FAILED)

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    @patch('apps.stores.services.mp_orders.create_order',
           return_value=_orders_rejeitando())
    def test_avulso_recusado_nao_explode(self, _criar, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_sdk_rejeitando()

        result = CheckoutService.create_payment(
            None, 'pix', amount=Decimal('25.00'), store=self.store,
        )

        self.assertFalse(result['success'])
        # Escopado à loja do teste: o test DB do compose carrega dados de seed.
        self.assertEqual(StorePayment.objects.filter(store=self.store).count(), 0)


class CheckoutViewPixFailureTests(APITestCase):
    """Nível view: 201 mantido, mas corpo diz payment_status='failed'."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-pixfail-view', password='x', email='owner-pfv@real.com',
        )
        self.store = Store.objects.create(
            name='Loja PixFail View', slug='loja-pixfail-view', owner=self.owner,
            status='active',
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-pixfail', is_active=True, sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Prato', slug='prato-pixfail',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
        )
        self.cart_key = 'cart-pixfail-view'
        self.cart = StoreCart.objects.create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=self.cart, product=self.product, quantity=1)

    def _checkout(self):
        payload = {
            'customer_name': 'Cliente View',
            'customer_email': 'cli-pfv@real.com',
            'customer_phone': '+5563999990000',
            'delivery_method': 'pickup',
            'payment_method': 'pix',
        }
        return self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            payload, format='json', HTTP_X_CART_KEY=self.cart_key,
        )

    @patch('apps.stores.services.print_service.enqueue_order_print_job')
    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_corpo_honesto_quando_pix_falha(self, _email, _print):
        with patch(
            'apps.stores.api.views.storefront_views.checkout_service.create_payment',
            return_value={'success': False, 'error': 'PIX indisponível'},
        ):
            resp = self._checkout()

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['payment_error'], 'PIX indisponível')
        # O corpo não pode fingir cobrança pendente
        self.assertEqual(resp.data['payment_status'], 'failed')
        # E não vem QR/código PIX fantasma
        self.assertFalse(resp.data.get('pix_code'))
        self.assertFalse(resp.data.get('pix_qr_code'))
