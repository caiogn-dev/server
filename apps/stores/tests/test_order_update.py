"""
Tests for StoreOrderUpdateSerializer — scheduling and editable order fields.

Verifica que o PATCH /api/v1/stores/{store_slug}/orders/{id}/ persiste
os campos de agendamento e dados do cliente adicionados na Fase 2 B1.
"""
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from apps.stores.models import Store, StoreOrder

User = get_user_model()


class OrderUpdateSchedulingTestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner1', email='owner1@example.com', password='x'
        )
        self.store = Store.objects.create(
            name='Loja 1', slug='loja-1', owner=self.owner, status='active'
        )
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Antigo',
            customer_phone='63999990000',
            subtotal=10,
            total=10,
        )
        self.url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/'

    def test_patch_scheduling_fields_persist(self):
        resp = self.client.patch(self.url, {
            'scheduled_date': '2999-01-15',
            'scheduled_time': '16:00-17:00',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(str(self.order.scheduled_date), '2999-01-15')
        self.assertEqual(self.order.scheduled_time, '16:00-17:00')

    def test_patch_customer_data_persist(self):
        resp = self.client.patch(self.url, {
            'customer_name': 'Novo Nome',
            'customer_phone': '63988887777',
            'customer_notes': 'Sem cebola',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_name, 'Novo Nome')
        self.assertEqual(self.order.customer_phone, '63988887777')
        self.assertEqual(self.order.customer_notes, 'Sem cebola')

    def test_patch_cannot_change_total(self):
        resp = self.client.patch(self.url, {'total': '99999'}, format='json')
        # total não está no serializer → ignorado, valor original mantido
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(str(self.order.total), '10.00')

    # -----------------------------------------------------------------------
    # M-1 + M-2: delivery_address validation
    # -----------------------------------------------------------------------

    def test_m2_patch_delivery_address_null_persists_empty_dict(self):
        """M-2: PATCH com delivery_address: null → 200 e persiste {} no banco."""
        resp = self.client.patch(self.url, {'delivery_address': None}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        # Deve ser um dict (vazio ou {}) — nunca None
        self.assertIsInstance(self.order.delivery_address, dict)

    def test_m1_patch_delivery_address_string_returns_400(self):
        """M-1: PATCH com delivery_address como string → 400 (não persiste)."""
        resp = self.client.patch(self.url, {'delivery_address': 'rua invalida'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_m1_patch_delivery_address_list_returns_400(self):
        """M-1: PATCH com delivery_address como lista → 400."""
        resp = self.client.patch(self.url, {'delivery_address': ['a', 'b']}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_patch_valid_delivery_address_dict_persists(self):
        """Sanidade: PATCH com dict válido → 200 e persiste."""
        addr = {'street': 'Rua das Flores', 'number': '42'}
        resp = self.client.patch(self.url, {'delivery_address': addr}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_address.get('street'), 'Rua das Flores')
