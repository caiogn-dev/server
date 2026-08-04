"""Regressão de segurança: IDOR + PII leak no debug action de CustomersViewSet [P0/P1].

Antes do fix:
- debug action: `permission_classes=[IsAuthenticated, IsAdminUser]` sem _user_can_use_store.
  Qualquer usuário com is_staff=True passava ?store=<uuid-loja-alheia> e recebia:
    - store_name, store_id
    - contagem de clientes, assinantes e pedidos de outro tenant
    - sample PII: id, email, first_name, last_name, date_joined de até 5 clientes

Fix: remover IsAdminUser; adicionar _user_can_use_store logo após validar store_id;
retornar 404 se usuário não tem acesso (info-hiding — mesmo comportamento do count action).

Técnica: SimpleTestCase + mocks. Sem Docker/PostgreSQL.
"""
import ast
import inspect
import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

_SETTINGS = dict(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (),
        'DEFAULT_PERMISSION_CLASSES': (),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    },
)

factory = APIRequestFactory()

VIEWS_PATH = os.path.join(
    os.path.dirname(__file__), 'api', 'views.py'
)


def _read_source():
    with open(VIEWS_PATH, 'r') as f:
        return f.read()


def _get_debug_block_source():
    """Retorna o bloco completo do debug action, incluindo decorators."""
    source = _read_source()
    lines = source.splitlines()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'CustomersViewSet':
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == 'debug':
                    # decorator_list começa antes do `def`
                    start_line = item.lineno - 1  # 0-indexed
                    if item.decorator_list:
                        start_line = item.decorator_list[0].lineno - 1
                    end_line = item.end_lineno  # inclusive
                    return '\n'.join(lines[start_line:end_line])
    return None


# ---------------------------------------------------------------------------
# Análise estática (sem instanciar views)
# ---------------------------------------------------------------------------

class TestDebugActionStaticAnalysis(SimpleTestCase):
    """Testes de análise estática — confirmam ausência de IsAdminUser no debug action."""

    def _get_debug_method_source(self):
        return _get_debug_block_source()

    def test_debug_action_exists_in_customers_viewset(self):
        """debug action deve existir em CustomersViewSet."""
        method_src = self._get_debug_method_source()
        self.assertIsNotNone(method_src, "debug action não encontrada em CustomersViewSet")

    def test_debug_action_does_not_use_is_admin_user(self):
        """IsAdminUser não deve aparecer no decorator do debug action (usa is_staff — bypass cross-tenant)."""
        method_src = self._get_debug_method_source()
        self.assertNotIn(
            'IsAdminUser', method_src,
            "debug action ainda usa IsAdminUser — qualquer is_staff acessa dados de qualquer tenant"
        )

    def test_debug_action_calls_user_can_use_store(self):
        """debug action deve chamar _user_can_use_store para gate de tenant."""
        method_src = self._get_debug_method_source()
        self.assertIn(
            '_user_can_use_store', method_src,
            "debug action não chama _user_can_use_store — sem gate de tenant"
        )

    def test_is_admin_user_not_imported_or_removed_from_debug(self):
        """IsAdminUser pode permanecer importado mas não deve ser usado no debug action."""
        method_src = self._get_debug_method_source()
        self.assertIsNotNone(method_src)
        # Se a action ainda referencia IsAdminUser em sua decoração, o fix está incompleto.
        self.assertNotIn('IsAdminUser', method_src)


# ---------------------------------------------------------------------------
# Testes funcionais (com mocks)
# ---------------------------------------------------------------------------

class TestCustomersDebugIDOR(SimpleTestCase):
    """Testes comportamentais do debug action com mocks — sem DB/Redis/Docker."""

    def _make_view(self):
        from apps.marketing.api.views import CustomersViewSet
        view = CustomersViewSet.as_view({'get': 'debug'})
        return view

    def _make_user(self, is_staff=False, is_superuser=False, is_authenticated=True):
        user = MagicMock()
        user.is_authenticated = is_authenticated
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        return user

    @override_settings(**_SETTINGS)
    def test_missing_store_param_returns_400(self):
        """Sem ?store= → 400 Bad Request."""
        view = self._make_view()
        user = self._make_user(is_staff=True)
        request = factory.get('/debug/')
        request.user = user
        response = view(request)
        self.assertEqual(response.status_code, 400)

    @override_settings(**_SETTINGS)
    def test_staff_user_cannot_access_other_tenant_debug(self):
        """is_staff sem acesso à loja deve receber 404 (info-hiding, não 403)."""
        view = self._make_view()
        user = self._make_user(is_staff=True, is_superuser=False)
        request = factory.get('/debug/', {'store': 'loja-vitima-uuid'})
        request.user = user

        with patch(
            'apps.marketing.api.views._user_can_use_store',
            return_value=False,
        ):
            response = view(request)

        self.assertEqual(
            response.status_code, 404,
            "is_staff sem acesso à loja recebeu dados de outro tenant (IDOR)"
        )

    @override_settings(**_SETTINGS)
    def test_authenticated_user_with_access_can_debug(self):
        """Usuário autenticado COM acesso à loja deve receber 200."""
        view = self._make_view()
        user = self._make_user(is_staff=False, is_superuser=False)
        store_id = 'minha-loja-uuid'
        request = factory.get('/debug/', {'store': store_id})
        request.user = user

        fake_store = MagicMock()
        fake_store.name = 'Minha Loja'

        with (
            patch('apps.marketing.api.views._user_can_use_store', return_value=True),
            patch('apps.stores.models.Store.objects') as mock_store_mgr,
            patch('apps.stores.models.StoreOrder.objects') as mock_order_mgr,
            patch('apps.stores.models.StoreCustomer.objects', MagicMock()),
            patch('django.contrib.auth.get_user_model') as mock_get_user_model,
            patch('apps.marketing.models.Subscriber.objects') as mock_sub_mgr,
        ):
            mock_store_mgr.get.return_value = fake_store
            mock_order_mgr.filter.return_value.exclude.return_value.count.return_value = 5
            mock_get_user_model.return_value.objects.filter.return_value.distinct.return_value.count.return_value = 3
            mock_get_user_model.return_value.objects.filter.return_value.distinct.return_value.values.return_value.__getitem__.return_value = []
            mock_sub_mgr.filter.return_value.count.return_value = 2
            response = view(request)

        self.assertEqual(response.status_code, 200)

    @override_settings(**_SETTINGS)
    def test_superuser_can_debug_any_store(self):
        """Superuser deve conseguir debugar qualquer loja (sem gate de tenant)."""
        view = self._make_view()
        user = self._make_user(is_staff=False, is_superuser=True)
        request = factory.get('/debug/', {'store': 'qualquer-loja-uuid'})
        request.user = user

        fake_store = MagicMock()
        fake_store.name = 'Loja Qualquer'

        with (
            patch('apps.marketing.api.views._user_can_use_store', return_value=True),
            patch('apps.stores.models.Store.objects') as mock_store_mgr,
            patch('apps.stores.models.StoreOrder.objects') as mock_order_mgr,
            patch('apps.stores.models.StoreCustomer.objects', MagicMock()),
            patch('django.contrib.auth.get_user_model') as mock_get_user_model,
            patch('apps.marketing.models.Subscriber.objects') as mock_sub_mgr,
        ):
            mock_store_mgr.get.return_value = fake_store
            mock_order_mgr.filter.return_value.exclude.return_value.count.return_value = 0
            mock_get_user_model.return_value.objects.filter.return_value.distinct.return_value.count.return_value = 0
            mock_get_user_model.return_value.objects.filter.return_value.distinct.return_value.values.return_value.__getitem__.return_value = []
            mock_sub_mgr.filter.return_value.count.return_value = 0
            response = view(request)

        self.assertEqual(response.status_code, 200)

    @override_settings(**_SETTINGS)
    def test_nonexistent_store_returns_404(self):
        """Store inexistente deve retornar 404, não 500."""
        from apps.stores.models import Store
        view = self._make_view()
        user = self._make_user(is_superuser=True)
        request = factory.get('/debug/', {'store': 'store-nao-existe'})
        request.user = user

        with (
            patch('apps.marketing.api.views._user_can_use_store', return_value=True),
            patch('apps.stores.models.Store.objects') as mock_store_mgr,
            patch('django.contrib.auth.get_user_model') as mock_get_user_model,
            patch('apps.marketing.models.Subscriber.objects') as mock_sub_mgr,
            patch('apps.stores.models.StoreCustomer.objects', MagicMock()),
        ):
            mock_store_mgr.get.side_effect = Store.DoesNotExist
            mock_get_user_model.return_value.objects.filter.return_value.distinct.return_value = MagicMock(count=lambda: 0)
            mock_sub_mgr.filter.return_value.count.return_value = 0
            response = view(request)

        self.assertEqual(response.status_code, 404)

    @override_settings(**_SETTINGS)
    def test_staff_user_no_access_does_not_receive_pii(self):
        """is_staff sem acesso NÃO deve receber qualquer dado de PII da loja alheia."""
        view = self._make_view()
        user = self._make_user(is_staff=True, is_superuser=False)
        request = factory.get('/debug/', {'store': 'loja-alheia'})
        request.user = user

        with patch('apps.marketing.api.views._user_can_use_store', return_value=False):
            response = view(request)

        # Garante que nenhum dado de loja, cliente ou assinante é retornado
        self.assertNotEqual(response.status_code, 200)
        if hasattr(response, 'data') and response.data:
            self.assertNotIn('store_name', response.data)
            self.assertNotIn('users', response.data)
            self.assertNotIn('subscribers', response.data)
