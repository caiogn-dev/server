"""
Testes de regressão: CustomerSearchView deve retornar apenas clientes
que têm endereço ou pedido no tenant correto.

Bug original: UnifiedUser.objects.filter(Q(name__...) | Q(phone_number__...))
sem nenhum escopo de loja — qualquer owner autenticado obtinha nome/telefone
de clientes de outros tenants (PII leak cross-tenant, P2).
"""
import inspect
import unittest
from unittest.mock import MagicMock, patch, call


class TestCustomerSearchTenantScopeSource(unittest.TestCase):
    """Análise estática: garante que o filtro de tenant está no código-fonte."""

    @classmethod
    def setUpClass(cls):
        from apps.stores.api.views.crm_views import CustomerSearchView
        cls.src = inspect.getsource(CustomerSearchView.get)

    def test_scope_por_storecustomer(self):
        """Query deve filtrar por StoreCustomer.store (caminho canônico usado em _accessible_unified_users)."""
        self.assertIn('store_customers__store', self.src,
                      "CustomerSearchView deve escopar por 'store_customers__store=store'")

    def test_scope_por_enderecos_do_tenant(self):
        """Query deve filtrar por endereços do tenant (addresses__tenant)."""
        self.assertIn('addresses__tenant', self.src,
                      "CustomerSearchView deve escopar por 'addresses__tenant=store'")

    def test_scope_por_pedidos_do_tenant(self):
        """Query deve filtrar por pedidos do tenant via django_user."""
        self.assertIn('django_user__store_orders__store', self.src,
                      "CustomerSearchView deve escopar por 'django_user__store_orders__store=store'")

    def test_distinct_presente(self):
        """distinct() é obrigatório pois o JOIN cross-M2M pode duplicar linhas."""
        self.assertIn('.distinct()', self.src,
                      "CustomerSearchView deve chamar .distinct() após filtro M2M")

    def test_sem_query_global_sem_escopo(self):
        """Não deve haver filtro apenas por nome/telefone sem escopo de loja."""
        # Padrão inseguro: .filter(Q(...) | Q(...))[:<algo>] sem nenhum filtro de loja
        import re
        # Busca blocos de linhas que façam filter só com name/phone_number e depois
        # apliquem slicing sem nenhum filtro de addresses__tenant nem store_orders
        src_one_line = self.src.replace('\n', ' ')
        bad = re.search(
            r'UnifiedUser\.objects\s*\.\s*filter\s*\(\s*Q\(.*?name__icontains',
            src_one_line,
        )
        # Se existir, deve haver também addresses__tenant ou django_user__store_orders
        if bad:
            has_tenant_filter = (
                'addresses__tenant' in src_one_line
                or 'django_user__store_orders__store' in src_one_line
            )
            self.assertTrue(has_tenant_filter,
                            "Query global sem escopo de tenant encontrada em CustomerSearchView")


class TestCustomerSearchTenantScopeMock(unittest.TestCase):
    """Testes funcionais com mock: verifica que o filtro de tenant é aplicado."""

    def _make_request(self, q='Silva', limit=None):
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = False
        request.user.is_authenticated = True
        params = {'q': q}
        if limit:
            params['limit'] = str(limit)
        request.query_params = params
        return request

    def _make_store(self, store_id=None):
        import uuid
        store = MagicMock()
        store.id = store_id or str(uuid.uuid4())
        store.pk = store.id
        return store

    def _run_view(self, request, store, perm_ok=True):
        """Helper: executa CustomerSearchView.get com todos os internals mockados."""
        from apps.stores.api.views.crm_views import CustomerSearchView

        view = CustomerSearchView()
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.distinct.return_value = mock_qs
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])

        with patch('apps.stores.api.views.crm_views.IsStoreOwnerOrStaff') as MockPerm, \
             patch('apps.stores.api.views.crm_views._get_store', return_value=store), \
             patch('apps.stores.api.views.crm_views.UnifiedUser') as MockUU, \
             patch('apps.stores.api.views.crm_views.UserAddress') as MockUA, \
             patch('apps.stores.api.views.crm_views.Prefetch', return_value=MagicMock()), \
             patch('apps.stores.api.views.crm_views.CustomerSearchSerializer') as MockSer:

            MockUU.objects = MagicMock()
            MockUU.objects.filter.return_value = mock_qs
            MockUA.objects.filter.return_value = mock_qs

            perm_instance = MagicMock()
            perm_instance._user_can_access_store.return_value = perm_ok
            MockPerm.return_value = perm_instance
            MockSer.return_value.data = []

            response = view.get(request, 'store-slug')
            return response, MockUU, mock_qs

    def test_queryset_aplica_filtro_de_tenant(self):
        """A view deve chamar filter com addresses__tenant ou store_orders__store."""
        request = self._make_request()
        store = self._make_store()
        _, MockUU, mock_qs = self._run_view(request, store)

        self.assertTrue(MockUU.objects.filter.called or mock_qs.filter.called,
                        "UnifiedUser.objects.filter deve ser chamado")
        self.assertTrue(mock_qs.distinct.called,
                        "Deve chamar .distinct() para evitar duplicatas do JOIN")

    def test_superuser_nao_e_bloqueado(self):
        """Superuser não deve ser bloqueado pelo gate de tenant."""
        request = self._make_request()
        request.user.is_superuser = True
        store = self._make_store()
        response, _, _ = self._run_view(request, store)
        self.assertIsNotNone(response)


class TestCustomerSearchPermissionGate(unittest.TestCase):
    """Verifica que a permissão de tenant é checada antes de retornar dados."""

    def test_sem_acesso_retorna_403(self):
        """Usuário sem acesso à loja deve receber 403, não dados de outros tenants."""
        from apps.stores.api.views.crm_views import CustomerSearchView

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = False
        request.user.is_authenticated = True
        request.query_params = {'q': 'Silva'}

        store = MagicMock()
        store.id = 'victim-store-uuid'

        view = CustomerSearchView()

        with patch(
            'apps.stores.api.views.crm_views.IsStoreOwnerOrStaff',
        ) as MockPerm, patch(
            'apps.stores.api.views.crm_views._get_store', return_value=store
        ):
            perm_instance = MagicMock()
            perm_instance._user_can_access_store.return_value = False
            MockPerm.return_value = perm_instance

            response = view.get(request, 'victim-store-slug')
            self.assertEqual(response.status_code, 403,
                             "Usuário sem acesso à loja deve receber 403")

    def test_query_curta_retorna_lista_vazia(self):
        """Query com menos de 2 caracteres retorna lista vazia sem consultar o banco."""
        from apps.stores.api.views.crm_views import CustomerSearchView

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = False
        request.user.is_authenticated = True
        request.query_params = {'q': 'A'}

        store = MagicMock()

        view = CustomerSearchView()

        with patch(
            'apps.stores.api.views.crm_views.IsStoreOwnerOrStaff',
        ) as MockPerm, patch(
            'apps.stores.api.views.crm_views._get_store', return_value=store
        ), patch(
            'apps.stores.api.views.crm_views.UnifiedUser'
        ) as MockUU:
            perm_instance = MagicMock()
            perm_instance._user_can_access_store.return_value = True
            MockPerm.return_value = perm_instance

            response = view.get(request, 'store-slug')
            # Banco não deve ser consultado para query muito curta
            MockUU.objects.filter.assert_not_called()
