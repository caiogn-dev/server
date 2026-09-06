"""Regressão de segurança: is_staff bypass em StoreProductTypeViewSet [P1].

Vetor: um usuário com is_staff=True (acesso ao /admin Django, sem relação com
propriedade de tenant) passava por `if self.action == 'list' and not user.is_staff`
e via product-types INATIVAS de qualquer loja — incluindo lojas de outros tenants
quando `?store=<slug-da-vitima>` era fornecido via query param.

Padrão do projeto: is_staff ≠ acesso cross-tenant; somente is_superuser tem esse
privilégio. A correção substitui `is_staff` por `is_superuser` no gate de
filtragem de inativos.

Técnica: SimpleTestCase + patch no ORM. Sem Docker/PostgreSQL.
"""
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Helpers de usuário
# ---------------------------------------------------------------------------

def _is_staff_user():
    """Usuário is_staff=True mas NÃO superuser — acesso ao Django /admin, sem permissão cross-tenant."""
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = False
    u.is_staff = True
    return u


def _regular_user():
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = False
    u.is_staff = False
    return u


def _superuser():
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = True
    u.is_staff = True
    return u


def _anon_user():
    u = MagicMock()
    u.is_authenticated = False
    u.is_superuser = False
    u.is_staff = False
    return u


# ---------------------------------------------------------------------------
# Auxiliar: rastreia se filter(is_active=True) foi chamado no queryset
# ---------------------------------------------------------------------------

class _ChainableMock:
    """Mock de queryset que rastreia se filter(is_active=True) foi chamado."""

    def __init__(self):
        self.is_active_filter_applied = False
        self._store_id_filter_applied = False

    def filter(self, **kwargs):
        if kwargs.get('is_active') is True:
            self.is_active_filter_applied = True
        if 'store__slug' in kwargs or 'store_id' in kwargs or 'store_id__in' in kwargs:
            self._store_id_filter_applied = True
        return self

    def none(self):
        return self

    def select_related(self, *args):
        return self

    def order_by(self, *args):
        return self


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestIsStaffBypassInProductTypeViewSet(SimpleTestCase):
    """is_staff NÃO deve ver product-types inativas sem ser dono da loja."""

    def _make_view(self, user, store_slug=None, store_param=None, action='list'):
        from apps.stores.api.views.product_views import StoreProductTypeViewSet
        view = StoreProductTypeViewSet()
        view.action = action

        request = MagicMock()
        request.user = user
        params = {}
        if store_param:
            params['store'] = store_param
        request.query_params = params

        view.request = request
        view.kwargs = {}
        if store_slug:
            view.kwargs['store_slug'] = store_slug

        return view

    def _run_get_queryset(self, view, qs):
        """Roda get_queryset mockando StoreProductType.objects e accessible_store_ids."""
        with patch('apps.stores.api.views.product_views.StoreProductType') as MockModel, \
             patch('apps.core.permissions.accessible_store_ids', return_value=[]):
            MockModel.objects.all.return_value = qs
            return view.get_queryset()

    # ------------------------------------------------------------------
    # Caso 1: usuário regular → filtro de ativo aplicado (sem mudança)
    # ------------------------------------------------------------------

    def test_regular_user_sees_only_active(self):
        qs = _ChainableMock()
        view = self._make_view(_regular_user())
        self._run_get_queryset(view, qs)
        self.assertTrue(qs.is_active_filter_applied,
                        "Usuário regular deve ver apenas product-types ativas")

    # ------------------------------------------------------------------
    # Caso 2: anônimo → filtro de ativo aplicado (sem mudança)
    # ------------------------------------------------------------------

    def test_anon_user_sees_only_active(self):
        qs = _ChainableMock()
        view = self._make_view(_anon_user())
        self._run_get_queryset(view, qs)
        self.assertTrue(qs.is_active_filter_applied,
                        "Anônimo deve ver apenas product-types ativas")

    # ------------------------------------------------------------------
    # Caso 3 (BUG): is_staff sem superuser → NÃO deve ver inativas
    # Esta assertion FALHA antes do fix (is_staff bypassa o filtro).
    # ------------------------------------------------------------------

    def test_is_staff_not_superuser_sees_only_active(self):
        qs = _ChainableMock()
        view = self._make_view(_is_staff_user())
        self._run_get_queryset(view, qs)
        self.assertTrue(
            qs.is_active_filter_applied,
            "is_staff (sem superuser) NÃO deve ver product-types inativas — "
            "is_staff não equivale a acesso cross-tenant"
        )

    # ------------------------------------------------------------------
    # Caso 4 (BUG): is_staff acessando loja alheia via ?store=slug
    # ------------------------------------------------------------------

    def test_is_staff_cross_store_sees_only_active(self):
        qs = _ChainableMock()
        view = self._make_view(_is_staff_user(), store_param='loja-da-vitima')
        self._run_get_queryset(view, qs)
        self.assertTrue(
            qs.is_active_filter_applied,
            "is_staff passando ?store=loja-alheia deve ver apenas tipos ativos"
        )

    # ------------------------------------------------------------------
    # Caso 5 (BUG): is_staff acessando loja alheia via store_slug URL
    # ------------------------------------------------------------------

    def test_is_staff_cross_store_slug_sees_only_active(self):
        qs = _ChainableMock()
        view = self._make_view(_is_staff_user(), store_slug='loja-da-vitima')
        self._run_get_queryset(view, qs)
        self.assertTrue(
            qs.is_active_filter_applied,
            "is_staff acessando store_slug da vítima deve ver apenas tipos ativos"
        )

    # ------------------------------------------------------------------
    # Caso 6: superuser → pode ver inativas (comportamento preservado)
    # ------------------------------------------------------------------

    def test_superuser_sees_inactive(self):
        qs = _ChainableMock()
        view = self._make_view(_superuser())
        self._run_get_queryset(view, qs)
        self.assertFalse(
            qs.is_active_filter_applied,
            "Superuser deve ver product-types inativas (sem filtro)"
        )

    # ------------------------------------------------------------------
    # Caso 7: ação não-list → filtro de ativo não aplicado (sem mudança)
    # ------------------------------------------------------------------

    def test_retrieve_action_does_not_filter_active(self):
        qs = _ChainableMock()
        view = self._make_view(_regular_user(), action='retrieve')
        self._run_get_queryset(view, qs)
        self.assertFalse(
            qs.is_active_filter_applied,
            "Ação 'retrieve' não deve aplicar filtro is_active"
        )

    # ------------------------------------------------------------------
    # Caso 8: análise estática — não há mais is_staff na condição de filtragem
    # ------------------------------------------------------------------

    def test_source_uses_is_superuser_not_is_staff(self):
        import inspect
        from apps.stores.api.views.product_views import StoreProductTypeViewSet
        source = inspect.getsource(StoreProductTypeViewSet.get_queryset)
        self.assertNotIn(
            'not self.request.user.is_staff',
            source,
            "Condição de filtragem de inativos NÃO deve usar is_staff — "
            "substitua por is_superuser"
        )
        self.assertIn(
            'is_superuser',
            source,
            "Condição de filtragem de inativos deve usar is_superuser"
        )
