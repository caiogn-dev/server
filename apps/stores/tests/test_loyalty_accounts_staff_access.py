"""Garante que LoyaltyAccountsView e ConquistasView permitem acesso ao staff
da loja, não só ao dono.

Bug (P2): ambas as views verificavam `store.owner_id == request.user.id`, o
que bloqueava funcionários cadastrados como staff — o padrão multi-tenant é
`user_can_access_store()`, que inclui owner, staff M2M e StoreTeamMember.

Sem banco: testes via análise estática do source + mocks de request/store.
"""
import inspect
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase


def _make_user(is_superuser=False, is_owner=False, store_id=1):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = is_superuser
    user.id = 999 if not is_owner else store_id
    return user


def _make_store(owner_id=1):
    store = MagicMock()
    store.owner_id = owner_id
    store.pk = 1
    store.slug = 'test-store'
    return store


def _make_request(user):
    req = MagicMock()
    req.user = user
    req.query_params = MagicMock()
    req.query_params.get = MagicMock(return_value=1)
    return req


class LoyaltyViewsSourceCodeTest(SimpleTestCase):
    """Análise estática: o padrão antigo não pode mais estar no source."""

    def _get_loyalty_source(self):
        from apps.stores.api.views import loyalty_views
        return inspect.getsource(loyalty_views)

    def test_owner_id_check_removido_das_views_de_acesso(self):
        """Nenhuma view de acesso pode usar `owner_id == request.user.id`."""
        source = self._get_loyalty_source()
        # O padrão antigo que bloqueava staff deve ter sido substituído
        self.assertNotIn(
            'store.owner_id == request.user.id',
            source,
            'Padrão legado owner_id == user.id encontrado nas views de fidelidade. '
            'Use user_can_access_store() para incluir staff da loja.'
        )

    def test_user_can_access_store_importado(self):
        """user_can_access_store deve estar importada no módulo."""
        from apps.stores.api.views import loyalty_views
        self.assertTrue(
            hasattr(loyalty_views, 'user_can_access_store'),
            'user_can_access_store não está importada em loyalty_views. '
            'Adicione: from apps.core.permissions import user_can_access_store'
        )


class LoyaltyAccountsViewPermissaoTest(SimpleTestCase):
    """Testa a verificação de acesso em LoyaltyAccountsView."""

    def _get_view(self):
        from apps.stores.api.views.loyalty_views import LoyaltyAccountsView
        return LoyaltyAccountsView()

    def _call_get(self, user, store_patch_return=None):
        from apps.stores.api.views.loyalty_views import LoyaltyAccountsView
        store = store_patch_return or _make_store(owner_id=1)
        request = _make_request(user)
        request.query_params = MagicMock()
        request.query_params.get = MagicMock(return_value=1)

        with patch(
            'apps.stores.api.views.loyalty_views.get_active_store',
            return_value=store,
        ), patch(
            'apps.stores.api.views.loyalty_views.user_can_access_store',
        ) as mock_access, patch(
            'apps.stores.api.views.loyalty_views.LoyaltyService._config',
            return_value=(10, True),
        ), patch(
            'apps.stores.api.views.loyalty_views.StoreLoyaltyAccount.objects.filter',
            return_value=MagicMock(
                select_related=MagicMock(
                    return_value=MagicMock(
                        annotate=MagicMock(
                            return_value=MagicMock(
                                order_by=MagicMock(return_value=[])
                            )
                        )
                    )
                )
            )
        ):
            yield mock_access, LoyaltyAccountsView().get(request, 'test-store')

    def test_superuser_pode_acessar(self):
        """Superuser deve ter acesso sem precisar de user_can_access_store."""
        user = _make_user(is_superuser=True)
        store = _make_store(owner_id=99)

        mock_qs = MagicMock()
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_qs.count.return_value = 0

        with patch('apps.stores.api.views.loyalty_views.get_active_store', return_value=store), \
             patch('apps.stores.api.views.loyalty_views.user_can_access_store', return_value=True) as mock_fn, \
             patch('apps.stores.api.views.loyalty_views.LoyaltyService._config', return_value=(10, True)), \
             patch('apps.stores.api.views.loyalty_views.StoreLoyaltyAccount.objects.filter',
                   return_value=MagicMock(
                       select_related=MagicMock(
                           return_value=MagicMock(
                               annotate=MagicMock(
                                   return_value=MagicMock(
                                       order_by=MagicMock(return_value=mock_qs)
                                   )
                               )
                           )
                       )
                   )):
            from apps.stores.api.views.loyalty_views import LoyaltyAccountsView
            request = _make_request(user)
            request.query_params.get = MagicMock(return_value=1)
            resp = LoyaltyAccountsView().get(request, 'test-store')
            self.assertEqual(resp.status_code, 200)

    def test_nao_membro_recebe_negativa(self):
        """Usuário sem acesso à loja deve receber 403 ou 404."""
        user = _make_user(is_superuser=False)
        store = _make_store(owner_id=99)

        with patch('apps.stores.api.views.loyalty_views.get_active_store', return_value=store), \
             patch('apps.stores.api.views.loyalty_views.user_can_access_store', return_value=False):
            from apps.stores.api.views.loyalty_views import LoyaltyAccountsView
            from django.http import Http404
            request = _make_request(user)
            try:
                resp = LoyaltyAccountsView().get(request, 'test-store')
                self.assertIn(resp.status_code, (403, 404),
                              'Não-membro deve receber 403 ou 404')
            except Http404:
                pass  # Http404 é aceito — info-hiding correto

    def test_user_can_access_store_chamado_para_nao_superuser(self):
        """user_can_access_store deve ser chamado para usuários não-superuser."""
        user = _make_user(is_superuser=False)
        store = _make_store(owner_id=99)

        with patch('apps.stores.api.views.loyalty_views.get_active_store', return_value=store), \
             patch('apps.stores.api.views.loyalty_views.user_can_access_store',
                   return_value=False) as mock_fn:
            from apps.stores.api.views.loyalty_views import LoyaltyAccountsView
            from django.http import Http404
            request = _make_request(user)
            try:
                LoyaltyAccountsView().get(request, 'test-store')
            except Http404:
                pass
            mock_fn.assert_called_once_with(user, store)


class ConquistasViewPermissaoTest(SimpleTestCase):
    """Testa a verificação de acesso em ConquistasView."""

    def test_user_can_access_store_chamado_para_nao_superuser(self):
        """user_can_access_store deve ser chamado para usuários não-superuser."""
        from apps.stores.api.views.loyalty_views import ConquistasView
        from django.http import Http404

        user = _make_user(is_superuser=False)
        store = _make_store(owner_id=99)
        request = _make_request(user)

        with patch('apps.stores.api.views.loyalty_views.get_active_store', return_value=store), \
             patch('apps.stores.api.views.loyalty_views.user_can_access_store',
                   return_value=False) as mock_fn:
            try:
                ConquistasView().get(request, 'test-store')
            except Http404:
                pass
            mock_fn.assert_called_once_with(user, store)

    def test_nao_membro_recebe_negativa(self):
        """Usuário sem acesso à loja deve receber 403 ou 404."""
        from apps.stores.api.views.loyalty_views import ConquistasView
        from django.http import Http404

        user = _make_user(is_superuser=False)
        store = _make_store(owner_id=99)
        request = _make_request(user)

        with patch('apps.stores.api.views.loyalty_views.get_active_store', return_value=store), \
             patch('apps.stores.api.views.loyalty_views.user_can_access_store', return_value=False):
            try:
                resp = ConquistasView().get(request, 'test-store')
                self.assertIn(resp.status_code, (403, 404))
            except Http404:
                pass

    def test_nao_contem_padrao_legado(self):
        """ConquistasView não deve usar owner_id == user.id."""
        import inspect
        from apps.stores.api.views import loyalty_views
        source = inspect.getsource(loyalty_views)
        self.assertNotIn(
            'store.owner_id == request.user.id',
            source,
            'ConquistasView ainda usa owner_id == user.id — use user_can_access_store()'
        )
