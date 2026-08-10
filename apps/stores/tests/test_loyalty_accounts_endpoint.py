from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreLoyaltyAccount

User = get_user_model()


class LoyaltyAccountsEndpointTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono4', password='x')
        self.other = User.objects.create_user(username='intruso', password='x')
        self.customer = User.objects.create_user(
            username='cli1', password='x', email='cli1@x.com', first_name='Ana')
        self.store = Store.objects.create(
            name='Loja', slug='loja-la', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 10},
        )
        StoreLoyaltyAccount.objects.create(
            store=self.store, user=self.customer, qualified_count=13, redeemed_count=1)
        self.url = f'/api/v1/stores/{self.store.slug}/loyalty/accounts/'

    def test_dono_lista_contas_com_progresso(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data['count'] == 1
        row = data['results'][0]
        assert row['qualified_count'] == 13
        assert row['progress'] == 3           # 13 % 10
        assert row['available_rewards'] == 0  # 13//10 - 1
        assert row['display_name'] == 'Ana'

    def test_nao_membro_recebe_404(self):
        self.client.force_authenticate(user=self.other)
        assert self.client.get(self.url).status_code == 404

    def test_anonimo_recebe_401(self):
        assert self.client.get(self.url).status_code == 401
