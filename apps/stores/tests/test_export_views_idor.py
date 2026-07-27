"""
Testes de regressão: IDOR em views de exportação (BaseExportView.get_store).

BaseExportView.get_store() buscava qualquer loja do banco sem checar acesso do
usuário autenticado — qualquer tenant autenticado exportava pedidos/PII de lojas
alheias via ?store=<slug> ou ?store=<uuid>.

Todos SimpleTestCase (sem DB/Docker) — testa a lógica de gate diretamente.
Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \
  python manage.py test apps.stores.tests.test_export_views_idor -v 2
"""
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from django.http import Http404

from apps.stores.api.export_views import BaseExportView


def _make_view():
    return BaseExportView()


def _make_request(store_param, is_superuser=False):
    user = MagicMock()
    user.is_superuser = is_superuser
    request = MagicMock()
    request.user = user
    request.query_params = {'store': store_param} if store_param is not None else {}
    return request, user


def _make_store(slug='test-store'):
    store = MagicMock()
    store.id = '11111111-1111-1111-1111-111111111111'
    store.slug = slug
    return store


class GetStoreTenantGateTest(SimpleTestCase):
    """gate anti-IDOR em BaseExportView.get_store — non-superuser sem acesso → 404."""

    def test_atacante_sem_acesso_obtem_404(self):
        """Usuário autenticado sem acesso à loja alvo → Http404 (info-hiding)."""
        view = _make_view()
        request, user = _make_request('loja-vitima', is_superuser=False)
        store = _make_store('loja-vitima')

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=False):
            mock_qs = MagicMock()
            mock_qs.first.return_value = store
            mock_mgr.filter.return_value = mock_qs

            with self.assertRaises(Http404):
                view.get_store(request)

    def test_dono_legítimo_recebe_store(self):
        """Usuário com acesso à loja recebe o objeto normalmente."""
        view = _make_view()
        request, user = _make_request('minha-loja', is_superuser=False)
        store = _make_store('minha-loja')

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=True):
            mock_qs = MagicMock()
            mock_qs.first.return_value = store
            mock_mgr.filter.return_value = mock_qs

            result = view.get_store(request)

        self.assertIs(result, store)

    def test_superuser_nao_passa_pelo_gate(self):
        """Superuser recebe a loja sem passar pela verificação de tenant."""
        view = _make_view()
        request, user = _make_request('qualquer-loja', is_superuser=True)
        store = _make_store('qualquer-loja')

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store') as mock_gate:
            mock_qs = MagicMock()
            mock_qs.first.return_value = store
            mock_mgr.filter.return_value = mock_qs

            result = view.get_store(request)

        self.assertIs(result, store)
        mock_gate.assert_not_called()

    def test_loja_inexistente_retorna_none(self):
        """Loja não encontrada retorna None — views respondem com 400 (comportamento original)."""
        view = _make_view()
        request, user = _make_request('nao-existe', is_superuser=False)

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=False):
            mock_qs = MagicMock()
            mock_qs.first.return_value = None
            mock_mgr.filter.return_value = mock_qs

            result = view.get_store(request)

        self.assertIsNone(result)

    def test_sem_parametro_store_retorna_none(self):
        """Sem parâmetro ?store na query → None sem chamar o banco."""
        view = _make_view()
        request = MagicMock()
        request.user = MagicMock()
        request.query_params = {}

        result = view.get_store(request)

        self.assertIsNone(result)

    def test_gate_chamado_com_user_e_store_corretos(self):
        """user_can_access_store recebe exatamente (user, store) como args."""
        view = _make_view()
        request, user = _make_request('minha-loja', is_superuser=False)
        store = _make_store('minha-loja')

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=True) as mock_gate:
            mock_qs = MagicMock()
            mock_qs.first.return_value = store
            mock_mgr.filter.return_value = mock_qs

            view.get_store(request)

        mock_gate.assert_called_once_with(user, store)

    def test_uuid_valido_atacante_obtem_404(self):
        """UUID válido de loja alheia também é bloqueado pelo gate de tenant."""
        view = _make_view()
        valid_uuid = '11111111-1111-1111-1111-111111111111'
        request, user = _make_request(valid_uuid, is_superuser=False)
        store = _make_store()

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=False):
            mock_mgr.get.return_value = store

            with self.assertRaises(Http404):
                view.get_store(request)

    def test_uuid_valido_dono_recebe_store(self):
        """UUID válido e dono da loja → objeto retornado normalmente."""
        view = _make_view()
        valid_uuid = '11111111-1111-1111-1111-111111111111'
        request, user = _make_request(valid_uuid, is_superuser=False)
        store = _make_store()

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=True):
            mock_mgr.get.return_value = store

            result = view.get_store(request)

        self.assertIs(result, store)

    def test_uuid_inexistente_retorna_none(self):
        """UUID válido mas loja não existe → None (not 500)."""
        view = _make_view()
        valid_uuid = '22222222-2222-2222-2222-222222222222'
        request, user = _make_request(valid_uuid, is_superuser=False)

        with patch('apps.stores.api.export_views.Store.objects') as mock_mgr, \
             patch('apps.stores.api.export_views.user_can_access_store', return_value=False):
            from apps.stores.models import Store as StoreModel
            mock_mgr.get.side_effect = StoreModel.DoesNotExist

            result = view.get_store(request)

        self.assertIsNone(result)
