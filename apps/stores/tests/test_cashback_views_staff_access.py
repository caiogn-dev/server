"""
Testes de controle de acesso para CashbackResumoView, CashbackAjusteView e
IndicacoesView.

Bug: as três views usavam `store.owner_id == request.user.id` em vez de
`user_can_access_store()`, bloqueando membros da equipe (M2M staff) que têm
acesso legítimo à loja.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store

User = get_user_model()


def _make_store(owner, slug='loja-cb-test'):
    return Store.objects.create(
        name='Loja CB', slug=slug, owner=owner, status='active',
    )


class CashbackResumoStaffAccessTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono_cb', password='x')
        self.staff = User.objects.create_user(username='func_cb', password='x')
        self.outsider = User.objects.create_user(username='forasteiro_cb', password='x')
        self.store = _make_store(self.owner)
        # Adiciona o funcionário como staff M2M da loja
        self.store.staff.add(self.staff)
        self.url = f'/api/v1/stores/{self.store.slug}/cashback/'

    def test_dono_acessa_resumo(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content

    def test_staff_acessa_resumo(self):
        """Membro da equipe deve conseguir ver o resumo do cashback."""
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(self.url)
        # Antes do fix retornava 403; depois deve retornar 200
        assert resp.status_code == 200, resp.content

    def test_superuser_acessa_resumo(self):
        su = User.objects.create_user(username='su_cb', password='x', is_superuser=True)
        self.client.force_authenticate(user=su)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content

    def test_forasteiro_recebe_404(self):
        """Usuário sem relação com a loja deve receber 404, não 403."""
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(self.url)
        assert resp.status_code == 404, resp.content

    def test_anonimo_recebe_401(self):
        resp = self.client.get(self.url)
        assert resp.status_code == 401, resp.content


class CashbackAjusteStaffAccessTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono_ajuste', password='x')
        self.staff = User.objects.create_user(username='func_ajuste', password='x')
        self.outsider = User.objects.create_user(username='fora_ajuste', password='x')
        self.store = _make_store(self.owner, slug='loja-ajuste-test')
        self.store.staff.add(self.staff)
        self.url = f'/api/v1/stores/{self.store.slug}/cashback/ajustar/'
        self.payload = {'phone': '11999990000', 'valor': '10.00', 'motivo': 'Teste'}

    def test_dono_pode_ajustar(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, self.payload)
        # 201 se o serviço encontrar o cliente, ou 400 se não — mas nunca 403
        assert resp.status_code in (201, 400), resp.content

    def test_staff_pode_ajustar(self):
        """Membro da equipe deve poder fazer ajuste manual de cashback."""
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(self.url, self.payload)
        # Antes do fix retornava 403; depois deve passar a checagem de permissão
        assert resp.status_code in (201, 400), resp.content

    def test_forasteiro_recebe_404(self):
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(self.url, self.payload)
        assert resp.status_code == 404, resp.content

    def test_anonimo_recebe_401(self):
        resp = self.client.post(self.url, self.payload)
        assert resp.status_code == 401, resp.content


class IndicacoesStaffAccessTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono_ind', password='x')
        self.staff = User.objects.create_user(username='func_ind', password='x')
        self.outsider = User.objects.create_user(username='fora_ind', password='x')
        self.store = _make_store(self.owner, slug='loja-ind-test')
        self.store.staff.add(self.staff)
        self.url = f'/api/v1/stores/{self.store.slug}/indicacoes/'

    def test_dono_acessa_indicacoes(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content

    def test_staff_acessa_indicacoes(self):
        """Membro da equipe deve conseguir ver as indicações."""
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(self.url)
        # Antes do fix retornava 403; depois deve retornar 200
        assert resp.status_code == 200, resp.content

    def test_superuser_acessa_indicacoes(self):
        su = User.objects.create_user(username='su_ind', password='x', is_superuser=True)
        self.client.force_authenticate(user=su)
        resp = self.client.get(self.url)
        assert resp.status_code == 200, resp.content

    def test_forasteiro_recebe_404(self):
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(self.url)
        assert resp.status_code == 404, resp.content

    def test_anonimo_recebe_401(self):
        resp = self.client.get(self.url)
        assert resp.status_code == 401, resp.content
