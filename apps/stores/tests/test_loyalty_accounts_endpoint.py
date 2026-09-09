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

    def test_nao_dono_recebe_403(self):
        self.client.force_authenticate(user=self.other)
        assert self.client.get(self.url).status_code == 403

    def test_anonimo_recebe_401(self):
        assert self.client.get(self.url).status_code == 401


class LoyaltyAccountsContatoTest(APITestCase):
    """A lista precisa dizer QUEM é o cliente.

    Ela mostrava nome + e-mail, e para quem entra por WhatsApp o e-mail é
    fabricado pelo backend (`84689350@local.invalid`): 30 das 84 contas da Cê
    Saladas exibiam isso cru. Sem telefone, "falta 1 para a Nair" não vira
    mensagem — não há como falar com a Nair a partir da tela.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='dono-ct', password='x')
        self.cliente = User.objects.create_user(
            username='cliente_5563984689350', password='x',
            email='84689350@local.invalid', first_name='Nair')
        self.store = Store.objects.create(
            name='Loja CT', slug='loja-ct', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 10})
        StoreLoyaltyAccount.objects.create(
            store=self.store, user=self.cliente, qualified_count=9, redeemed_count=0)
        self.url = f'/api/v1/stores/{self.store.slug}/loyalty/accounts/'

    def test_linha_traz_o_telefone_do_cliente(self):
        self.client.force_authenticate(user=self.owner)
        row = self.client.get(self.url).json()['results'][0]
        assert row['phone'] == '5563984689350'
