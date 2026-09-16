"""Testes de regressão: IDOR em gerar_codigos_internos [P0]

Vetor: POST /api/v1/stores/products/gerar-codigos-internos/ com {"store": "<uuid-loja-alheia>"}
via rota plana (sem store_pk na URL). IsStoreOwnerOrStaff retorna True para qualquer
autenticado quando store_pk não está nos kwargs — o gate de tenant precisava estar
dentro da action.
"""
import inspect
import uuid
from unittest.mock import MagicMock, patch, PropertyMock
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Análise estática: o fix deve adicionar user_can_access_store na action
# ---------------------------------------------------------------------------

class TestBarcodeEndpointStaticAnalysis(SimpleTestCase):
    """Garante que a função de gate de tenant está importada e usada na action."""

    def _get_product_views_source(self):
        import apps.stores.api.views.product_views as mod
        return inspect.getsource(mod)

    def test_user_can_access_store_importado(self):
        """user_can_access_store deve estar importado no módulo de product views."""
        source = self._get_product_views_source()
        self.assertIn('user_can_access_store', source,
                      "user_can_access_store deve ser importado em product_views.py")

    def test_gerar_codigos_internos_chama_gate_de_tenant(self):
        """A action gerar_codigos_internos deve chamar user_can_access_store."""
        import apps.stores.api.views.product_views as mod
        from apps.stores.api.views.product_views import StoreProductViewSet
        source = inspect.getsource(StoreProductViewSet.gerar_codigos_internos)
        self.assertIn('user_can_access_store', source,
                      "gerar_codigos_internos deve chamar user_can_access_store para isolar tenant")

    def test_gerar_codigos_internos_retorna_404_quando_sem_acesso(self):
        """Sem acesso à loja, a action deve retornar 404 (info-hiding)."""
        import apps.stores.api.views.product_views as mod
        from apps.stores.api.views.product_views import StoreProductViewSet
        source = inspect.getsource(StoreProductViewSet.gerar_codigos_internos)
        self.assertIn('Http404', source,
                      "gerar_codigos_internos deve levantar Http404 quando acesso negado")


# ---------------------------------------------------------------------------
# Testes comportamentais com mocks (sem DB)
# ---------------------------------------------------------------------------

class TestBarcodeEndpointTenantGate(SimpleTestCase):
    """Verifica o comportamento de tenant gate da action via mocks."""

    def _make_request(self, user, data):
        req = MagicMock()
        req.user = user
        req.data = data
        return req

    def _make_view(self, store_pk=None):
        from apps.stores.api.views.product_views import StoreProductViewSet
        view = StoreProductViewSet()
        view.kwargs = {}
        if store_pk:
            view.kwargs['store_pk'] = store_pk
        view.format_kwarg = None
        view.request = None
        return view

    def _make_non_superuser(self):
        user = MagicMock()
        user.is_superuser = False
        user.is_authenticated = True
        return user

    def _make_superuser(self):
        user = MagicMock()
        user.is_superuser = True
        user.is_authenticated = True
        return user

    def test_atacante_sem_acesso_recebe_404_via_rota_plana(self):
        """Atacante com token de loja A que tenta body com loja B → 404."""
        from django.http import Http404
        from apps.stores.api.views.product_views import StoreProductViewSet

        loja_vitima = MagicMock()
        loja_vitima.id = uuid.uuid4()

        user = self._make_non_superuser()
        request = self._make_request(user, {"store": str(loja_vitima.id)})

        view = self._make_view(store_pk=None)  # rota plana: sem store_pk

        with patch('apps.stores.api.views.product_views.Store') as MockStore, \
             patch('apps.stores.api.views.product_views.user_can_access_store',
                   return_value=False) as mock_gate:

            mock_qs = MagicMock()
            MockStore.objects.filter.return_value.first.return_value = loja_vitima
            MockStore.objects.order_by.return_value.values_list.return_value = []

            with self.assertRaises(Http404):
                view.gerar_codigos_internos(request, store_pk=None)

            mock_gate.assert_called_once_with(user, loja_vitima)

    def test_dono_da_loja_recebe_200(self):
        """Usuário com acesso à loja consegue gerar os códigos normalmente."""
        from apps.stores.api.views.product_views import StoreProductViewSet
        from rest_framework.response import Response

        loja = MagicMock()
        loja.id = uuid.uuid4()

        user = self._make_non_superuser()
        request = self._make_request(user, {"store": str(loja.id)})

        view = self._make_view(store_pk=None)

        with patch('apps.stores.api.views.product_views.Store') as MockStore, \
             patch('apps.stores.api.views.product_views.user_can_access_store',
                   return_value=True), \
             patch('apps.stores.api.views.product_views.StoreProduct') as MockProduct, \
             patch('apps.stores.api.views.product_views.transaction') as MockTx:

            MockStore.objects.filter.return_value.first.return_value = loja
            all_ids = [uuid.uuid4()]
            MockStore.objects.order_by.return_value.values_list.return_value = [loja.id]

            # Simula queryset vazio (nenhum produto sem código)
            MockProduct.objects.filter.return_value.filter.return_value.filter.\
                return_value.order_by.return_value = []
            MockProduct.objects.filter.return_value.exclude.return_value.\
                values_list.return_value = []

            MockTx.atomic.return_value.__enter__ = lambda s: None
            MockTx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            response = view.gerar_codigos_internos(request, store_pk=None)

        self.assertEqual(response.data['total'], 0)

    def test_superuser_nao_precisa_de_gate(self):
        """Superuser bypass: não chama user_can_access_store."""
        from apps.stores.api.views.product_views import StoreProductViewSet

        loja = MagicMock()
        loja.id = uuid.uuid4()

        user = self._make_superuser()
        request = self._make_request(user, {"store": str(loja.id)})

        view = self._make_view(store_pk=None)

        with patch('apps.stores.api.views.product_views.Store') as MockStore, \
             patch('apps.stores.api.views.product_views.user_can_access_store') as mock_gate, \
             patch('apps.stores.api.views.product_views.StoreProduct') as MockProduct, \
             patch('apps.stores.api.views.product_views.transaction') as MockTx:

            MockStore.objects.filter.return_value.first.return_value = loja
            MockStore.objects.order_by.return_value.values_list.return_value = [loja.id]

            MockProduct.objects.filter.return_value.filter.return_value.filter.\
                return_value.order_by.return_value = []
            MockProduct.objects.filter.return_value.exclude.return_value.\
                values_list.return_value = []

            MockTx.atomic.return_value.__enter__ = lambda s: None
            MockTx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            view.gerar_codigos_internos(request, store_pk=None)

        mock_gate.assert_not_called()

    def test_loja_nao_encontrada_retorna_400(self):
        """Identificador inválido/inexistente → 400 com mensagem informativa."""
        from apps.stores.api.views.product_views import StoreProductViewSet

        user = self._make_non_superuser()
        request = self._make_request(user, {})  # sem campo "store"

        view = self._make_view(store_pk=None)

        with patch('apps.stores.api.views.product_views.Store') as MockStore:
            MockStore.objects.filter.return_value.first.return_value = None

            response = view.gerar_codigos_internos(request, store_pk=None)

        self.assertEqual(response.status_code, 400)

    def test_store_pk_na_url_usa_gate_via_permission_class(self):
        """Quando store_pk está na URL, IsStoreOwnerOrStaff já gateia — action
        não precisa chamar user_can_access_store de novo. Verificamos que o
        fluxo funciona (retorna algo útil) sem levantar 404 por acesso negado."""
        from apps.stores.api.views.product_views import StoreProductViewSet

        loja = MagicMock()
        loja.id = uuid.uuid4()
        store_pk = str(loja.id)

        user = self._make_non_superuser()
        request = self._make_request(user, {})  # store vem do store_pk na URL

        view = self._make_view(store_pk=store_pk)

        with patch('apps.stores.api.views.product_views.Store') as MockStore, \
             patch('apps.stores.api.views.product_views.user_can_access_store',
                   return_value=True), \
             patch('apps.stores.api.views.product_views.StoreProduct') as MockProduct, \
             patch('apps.stores.api.views.product_views.transaction') as MockTx:

            MockStore.objects.filter.return_value.first.return_value = loja
            MockStore.objects.order_by.return_value.values_list.return_value = [loja.id]

            MockProduct.objects.filter.return_value.filter.return_value.filter.\
                return_value.order_by.return_value = []
            MockProduct.objects.filter.return_value.exclude.return_value.\
                values_list.return_value = []

            MockTx.atomic.return_value.__enter__ = lambda s: None
            MockTx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            response = view.gerar_codigos_internos(request, store_pk=store_pk)

        self.assertIn('gerados', response.data)
