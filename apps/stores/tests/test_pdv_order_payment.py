"""PDV (painel): criar pedido deve gerar o pagamento PIX automaticamente."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct

User = get_user_model()


class PdvOrderPaymentTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-pdv', email='owner-pdv@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja PDV', slug='loja-pdv', owner=self.owner, status='active',
        )
        category = StoreCategory.objects.create(store=self.store, name='Saladas', slug='saladas')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=30, track_stock=False, category=category,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def _payload(self, payment_method='pix'):
        return {
            'store': str(self.store.id),
            'customer_name': 'Cliente PDV',
            'customer_phone': '5599999999999',
            'delivery_method': 'pickup',
            'payment_method': payment_method,
            'items': [{'product_id': str(self.product.id), 'quantity': 1}],
        }

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_pedido_pix_gera_pagamento(self, mock_create_payment):
        def fake_create_payment(order, payment_method='pix', payment_data=None):
            order.pix_code = 'PIXCODE123'
            order.pix_ticket_url = 'https://mp.example/ticket'
            order.save(update_fields=['pix_code', 'pix_ticket_url'])
            return {'success': True, 'pix_code': 'PIXCODE123'}

        mock_create_payment.side_effect = fake_create_payment

        resp = self.client.post(self.url, self._payload('pix'), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        mock_create_payment.assert_called_once()
        self.assertEqual(resp.data.get('pix_code'), 'PIXCODE123')
        self.assertEqual(resp.data.get('pix_ticket_url'), 'https://mp.example/ticket')

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_pedido_dinheiro_nao_chama_mercadopago(self, mock_create_payment):
        resp = self.client.post(self.url, self._payload('cash'), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        mock_create_payment.assert_not_called()

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_desconto_e_acrescimo_entram_no_total_do_pix(self, mock_create_payment):
        captured = {}

        def fake_create_payment(order, payment_method='pix', payment_data=None):
            captured['total'] = order.total
            return {'success': True}

        mock_create_payment.side_effect = fake_create_payment

        payload = self._payload('pix')
        payload['discount'] = '5.00'
        payload['surcharge'] = '2.50'
        resp = self.client.post(self.url, payload, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        # produto 30 - 5 + 2.50 = 27.50
        self.assertEqual(str(resp.data['total']), '27.50')
        self.assertEqual(str(captured['total']), '27.50')

    @patch('apps.stores.services.checkout_service.CheckoutService.create_payment')
    def test_falha_no_gateway_nao_quebra_criacao_do_pedido(self, mock_create_payment):
        mock_create_payment.side_effect = ValueError('Credenciais de pagamento nao configuradas')
        resp = self.client.post(self.url, self._payload('pix'), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn('payment_error', resp.data)
