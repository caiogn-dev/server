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
