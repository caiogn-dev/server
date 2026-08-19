"""pix_recipient_name — nome do titular da conta MP exposto pro storefront.

Contexto: o banco do pagador mostra o titular real da chave (DICT/Bacen), que
hoje é a razão social do MEI ("Caio Goncalves Nascimento") e não "Cardapidex".
O storefront exibe um aviso para o cliente não estranhar o nome. A fonte é a
env MERCADO_PAGO_RECIPIENT_NAME (segue o token global; quando houver gateway
por loja, o campo pode migrar pro gateway).

- OrderByTokenView inclui pix_recipient_name no bloco PIX.
- CheckoutService.create_payment (pix) inclui pix_recipient_name no retorno.
- Sem env configurada → string vazia (frontend esconde o aviso).
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


def _orders_pix(payment_id='MP123'):
    """Resposta 201 da Orders API para PIX (formato real capturado em 19/08)."""
    return (201, {
        'status': 'action_required',
        'status_detail': 'waiting_transfer',
        'transactions': {'payments': [{
            'id': payment_id,
            'status': 'action_required',
            'status_detail': 'waiting_transfer',
            'date_of_expiration': '2026-12-31T23:59:59.000-03:00',
            'payment_method': {
                'id': 'pix',
                'type': 'bank_transfer',
                'qr_code': f'PIXCOPIACOLA-{payment_id}',
                'qr_code_base64': 'BASE64IMG',
                'ticket_url': f'https://mp.example/{payment_id}',
            },
        }]},
    })


class PixRecipientNameTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-prn', password='x', email='owner@real.com',
        )
        self.store = Store.objects.create(
            name='Loja PRN', slug='loja-prn', owner=self.owner, status='active',
        )

    def _pix_order(self):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            customer_email='cli@real.com',
            subtotal=Decimal('50.00'), total=Decimal('50.00'),
            payment_method='pix', pix_code='PIXCODE', pix_qr_code='B64',
        )

    @override_settings(MERCADO_PAGO_RECIPIENT_NAME='Caio Goncalves Nascimento')
    def test_by_token_includes_recipient_name_for_pix(self):
        order = self._pix_order()
        resp = self.client.get(f'/api/v1/stores/orders/by-token/{order.access_token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['pix_recipient_name'], 'Caio Goncalves Nascimento')

    @override_settings(MERCADO_PAGO_RECIPIENT_NAME='')
    def test_by_token_recipient_name_empty_when_unset(self):
        order = self._pix_order()
        resp = self.client.get(f'/api/v1/stores/orders/by-token/{order.access_token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['pix_recipient_name'], '')

    def test_by_token_no_recipient_name_for_non_pix(self):
        order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            subtotal=Decimal('50.00'), total=Decimal('50.00'), payment_method='cash',
        )
        resp = self.client.get(f'/api/v1/stores/orders/by-token/{order.access_token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('pix_recipient_name', resp.data)

    @override_settings(MERCADO_PAGO_RECIPIENT_NAME='Caio Goncalves Nascimento')
    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN', 'provider': 'mercadopago'})
    @patch('apps.stores.services.mp_orders.create_order')
    def test_create_payment_pix_returns_recipient_name(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _orders_pix('MPRN1')
        order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            customer_email='cli@real.com',
            subtotal=Decimal('50.00'), total=Decimal('50.00'),
        )
        result = CheckoutService.create_payment(order, 'pix')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['pix_recipient_name'], 'Caio Goncalves Nascimento')
