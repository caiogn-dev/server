"""PDV (painel): criar pedido com customer_email nulo não pode dar 400.

Bug real (08/jul): cliente cadastrada em outra loja (Pastita) selecionada no
PDV da Kero Kero — o dash manda customer_email: null (objeto do picker vem sem
email) e o serializer rejeitava com "Este campo pode não ser nulo".
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct

User = get_user_model()


class PdvOrderNullEmailTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-nullmail', email='owner-nullmail@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Null Email', slug='loja-null-email', owner=self.owner, status='active',
        )
        category = StoreCategory.objects.create(store=self.store, name='Saladas', slug='saladas')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Salada', price=30, track_stock=False, category=category,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def _payload(self, **overrides):
        payload = {
            'store': str(self.store.id),
            'customer_name': 'Cliente Cross Loja',
            'customer_phone': '5599999990000',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            'items': [{'product_id': str(self.product.id), 'quantity': 1}],
        }
        payload.update(overrides)
        return payload

    def test_customer_email_null_cria_pedido(self):
        resp = self.client.post(self.url, self._payload(customer_email=None), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        # fallback existente: email sintético para cliente sem email
        self.assertIn('@local.invalid', resp.data.get('customer_email', ''))

    def test_customer_email_vazio_continua_ok(self):
        resp = self.client.post(self.url, self._payload(customer_email=''), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_customer_email_valido_continua_ok(self):
        resp = self.client.post(self.url, self._payload(customer_email='cliente@teste.com'), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data.get('customer_email'), 'cliente@teste.com')
