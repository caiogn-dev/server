from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class LoyaltyGuestStatusTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-guest', password='x')
        self.customer = User.objects.create_user(
            username='cli-guest', password='x', email='cli-guest@x.com', first_name='Ana')
        self.store = Store.objects.create(
            name='Loja Guest', slug='loja-guest', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 10},
        )
        self.phone = '5511999998888'
        for _ in range(13):
            StoreOrder.objects.create(
                store=self.store, customer=self.customer, customer_phone=self.phone,
                status='delivered', subtotal=10, total=10,
            )
        self.url = f'/api/v1/stores/{self.store.slug}/loyalty/guest-status/'

    def test_telefone_com_pedidos_devolve_progresso_real(self):
        resp = self.client.post(self.url, {'phone': self.phone}, format='json')
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data['threshold'] == 10
        assert data['enabled'] is True
        # progresso real: houve backfill a partir do histórico de pedidos
        assert isinstance(data['qualified_salads'], int)

    def test_telefone_desconhecido_devolve_zeros(self):
        resp = self.client.post(self.url, {'phone': '5511900000000'}, format='json')
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data['qualified_salads'] == 0
        assert data['available_rewards'] == 0
        assert data['can_redeem'] is False
        assert data['threshold'] == 10
        assert data['enabled'] is True

    def test_sem_phone_no_body_devolve_zeros_sem_500(self):
        resp = self.client.post(self.url, {}, format='json')
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data['qualified_salads'] == 0
        assert data['threshold'] == 10

    def test_resposta_nao_contem_pii(self):
        resp = self.client.post(self.url, {'phone': self.phone}, format='json')
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert 'name' not in data
        assert 'email' not in data
        assert 'display_name' not in data
        assert 'Ana' not in resp.content.decode()
        assert 'cli-guest@x.com' not in resp.content.decode()
