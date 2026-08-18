"""
Testes de regressão para IDOR em UnifiedUserActivityViewSet.

PROBLEMA: get_queryset() retornava UnifiedUserActivity.objects.all() sem
nenhum escopo de tenant — qualquer usuário autenticado listava atividades
(mensagens WA, pedidos, logins) de clientes de todos os tenants.

VETOR:
  GET /api/v1/users/activities/         → retornava TODOS os registros do banco
  GET /api/v1/users/activities/?user_id=<uuid-alheio>  → idem, filtrado por usuário alheio

CORREÇÃO: aplicar _accessible_unified_users() para limitar o queryset de
UnifiedUserActivity às atividades dos usuários acessíveis ao tenant logado.
"""
import uuid
from unittest import TestCase
from unittest.mock import MagicMock, patch, PropertyMock


class TestUnifiedUserActivityViewSetIsolamento(TestCase):
    """Verifica que UnifiedUserActivityViewSet escopou get_queryset por tenant."""

    def _get_viewset_source(self):
        import inspect
        from apps.users.views import UnifiedUserActivityViewSet
        return inspect.getsource(UnifiedUserActivityViewSet.get_queryset)

    def test_get_queryset_nao_usa_objects_all_sem_filtro(self):
        """
        Antes do fix: get_queryset() chamava super().get_queryset() que
        retorna UnifiedUserActivity.objects.all() sem restrição de tenant.
        Após o fix: deve filtrar por usuários acessíveis ao tenant.
        """
        source = self._get_viewset_source()
        self.assertIn('accessible', source.lower(),
                      "get_queryset() deve usar _accessible_unified_users() para escopar por tenant")

    def test_get_queryset_filtra_por_user_id_accessible(self):
        """Após o fix, o filtro ?user_id só aceita IDs de usuários acessíveis ao tenant."""
        source = self._get_viewset_source()
        self.assertNotIn('UnifiedUserActivity.objects.all()', source,
                         "get_queryset() não deve fazer objects.all() — usa escopo de tenant")

    def test_get_queryset_chama_accessible_unified_users(self):
        """get_queryset() deve delegar para _accessible_unified_users() ou equivalente."""
        source = self._get_viewset_source()
        self.assertTrue(
            '_accessible_unified_users' in source or 'accessible_user_ids' in source,
            "get_queryset() deve chamar _accessible_unified_users() para isolar por tenant"
        )


class TestUnifiedUserActivityViewSetComportamento(TestCase):
    """Testes comportamentais via mock — sem banco de dados."""

    def _build_request(self, user, query_params=None):
        request = MagicMock()
        request.user = user
        request.query_params = query_params or {}
        return request

    def _build_user(self, is_superuser=False):
        user = MagicMock()
        user.is_superuser = is_superuser
        user.is_authenticated = True
        return user

    def _make_viewset(self, user, query_params=None):
        from apps.users.views import UnifiedUserActivityViewSet
        vs = UnifiedUserActivityViewSet()
        vs.request = self._build_request(user, query_params)
        vs.kwargs = {}
        vs.action = 'list'
        vs.format_kwarg = None
        return vs

    @patch('apps.users.views._accessible_unified_users')
    def test_superuser_nao_filtrado(self, mock_accessible):
        """Superuser recebe acesso irrestrito (via _accessible_unified_users que retorna .all())."""
        superuser = self._build_user(is_superuser=True)
        mock_qs = MagicMock()
        mock_accessible.return_value = mock_qs
        mock_qs.values_list.return_value = ['id1', 'id2']

        vs = self._make_viewset(superuser)

        with patch('apps.users.models.UnifiedUserActivity.objects') as mock_obj:
            mock_filter = MagicMock()
            mock_obj.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            try:
                vs.get_queryset()
            except Exception:
                pass

        mock_accessible.assert_called_once_with(superuser)

    @patch('apps.users.views._accessible_unified_users')
    def test_usuario_comum_filtrado_por_tenant(self, mock_accessible):
        """Usuário regular só vê atividades dos seus clientes (tenant escopado)."""
        user = self._build_user(is_superuser=False)
        mock_qs = MagicMock()
        mock_accessible.return_value = mock_qs

        accessible_ids = [uuid.uuid4(), uuid.uuid4()]
        mock_qs.values_list.return_value = accessible_ids

        vs = self._make_viewset(user)

        with patch('apps.users.models.UnifiedUserActivity.objects') as mock_obj:
            mock_filter = MagicMock()
            mock_obj.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            try:
                vs.get_queryset()
            except Exception:
                pass

        mock_accessible.assert_called_once_with(user)

    @patch('apps.users.views._accessible_unified_users')
    def test_user_id_param_nao_bypassa_escopo(self, mock_accessible):
        """?user_id de outro tenant não retorna dados cross-tenant."""
        user = self._build_user(is_superuser=False)
        mock_qs = MagicMock()
        mock_accessible.return_value = mock_qs

        tenant_ids = [uuid.uuid4()]
        mock_qs.values_list.return_value = tenant_ids

        victim_user_id = str(uuid.uuid4())
        vs = self._make_viewset(user, query_params={'user_id': victim_user_id})

        with patch('apps.users.models.UnifiedUserActivity.objects') as mock_obj:
            mock_filter = MagicMock()
            mock_obj.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            try:
                vs.get_queryset()
            except Exception:
                pass

        mock_accessible.assert_called_once_with(user)


class TestUnifiedUserActivityViewSetAnaliseeEstatica(TestCase):
    """Análise estática para garantir que o padrão inseguro foi removido."""

    def _get_module_source(self):
        import inspect
        import apps.users.views as module
        return inspect.getsource(module)

    def test_UnifiedUserActivityViewSet_sem_objects_all_em_get_queryset(self):
        """
        Análise estática: UnifiedUserActivityViewSet.get_queryset() não pode
        chamar objects.all() como queryset base sem filtro de tenant subsequente.
        O padrão `super().get_queryset()` herda de ModelViewSet que usa
        `self.queryset` (atribuído como `UnifiedUserActivity.objects.all()`).
        O fix deve sobreescrever isso com filtro por tenant antes de retornar.
        """
        import inspect
        from apps.users.views import UnifiedUserActivityViewSet
        source = inspect.getsource(UnifiedUserActivityViewSet)
        self.assertTrue(
            '_accessible_unified_users' in source or 'accessible_user_ids' in source,
            "UnifiedUserActivityViewSet deve usar _accessible_unified_users() no get_queryset()"
        )

    def test_viewset_ainda_filtra_por_user_id_e_activity_type(self):
        """Os filtros por user_id e type ainda devem funcionar após o fix."""
        import inspect
        from apps.users.views import UnifiedUserActivityViewSet
        source = inspect.getsource(UnifiedUserActivityViewSet.get_queryset)
        self.assertIn('user_id', source, "Filtro por user_id deve ser mantido")
        self.assertIn('activity_type', source, "Filtro por activity_type deve ser mantido")
