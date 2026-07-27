"""Regressão de segurança: IDOR em StoreReviewListView [P1].

Antes do fix, IsStoreOwnerOrStaff.has_permission() só verificava ownership
quando 'store_pk' estava nos kwargs do router. A rota de listagem de avaliações
usa 'store_slug' — então has_permission() sempre retornava True para qualquer
usuário autenticado.

Vetor concreto: GET /api/v1/stores/{slug-da-vítima}/reviews/ retornava as
avaliações e dados dos pedidos de qualquer loja sem verificação de acesso.

Fix: get_queryset levanta Http404 quando o usuário não tem acesso à loja
(mesmo comportamento das views de caixa — sem revelar se a loja existe).

Técnica: SimpleTestCase + mocks. Sem Docker/PostgreSQL.
"""
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
)

factory = APIRequestFactory()

_VIEW = 'apps.stores.api.views.review_views'


def _attacker():
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = False
    u.is_staff = False
    return u


def _owner():
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


def _fake_store():
    s = MagicMock()
    s.slug = 'vitima-store'
    return s


def _empty_qs():
    """MagicMock que simula queryset vazio serializável."""
    qs = MagicMock()
    qs.select_related.return_value = qs
    qs.filter.return_value = qs
    qs.__iter__ = MagicMock(return_value=iter([]))
    qs.__len__ = MagicMock(return_value=0)
    qs.count = MagicMock(return_value=0)
    return qs


@override_settings(**_SETTINGS)
class StoreReviewListIDORTest(SimpleTestCase):
    """StoreReviewListView: atacante não pode ler avaliações de loja alheia."""

    def _call(self, user, store=None, can_access=False):
        from apps.stores.api.views.review_views import StoreReviewListView
        req = factory.get('/reviews/')
        req._force_auth_user = user
        with patch(f'{_VIEW}.Store.objects') as mock_store_mgr, \
             patch(f'{_VIEW}.StoreReview.objects') as mock_review_mgr, \
             patch(f'{_VIEW}.user_can_access_store', return_value=can_access):
            mock_store_mgr.filter.return_value.first.return_value = store
            mock_review_mgr.filter.return_value = _empty_qs()
            resp = StoreReviewListView.as_view()(req, store_slug='vitima-store')
        return resp

    def test_atacante_sem_acesso_recebe_404(self):
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404,
                         "Atacante sem acesso deve receber 404, não listar avaliações (evita IDOR)")

    def test_loja_inexistente_retorna_404(self):
        resp = self._call(_attacker(), store=None, can_access=False)
        self.assertEqual(resp.status_code, 404)

    def test_acesso_nao_revela_existencia_da_loja(self):
        """404 tanto para loja inexistente quanto para loja sem acesso (info-hiding)."""
        sem_loja = self._call(_attacker(), store=None, can_access=False)
        com_loja_sem_acesso = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(sem_loja.status_code, 404)
        self.assertEqual(com_loja_sem_acesso.status_code, 404)

    def test_dono_com_acesso_passa_pelo_gate(self):
        """Proprietário legítimo deve receber lista de avaliações (200)."""
        resp = self._call(_owner(), store=_fake_store(), can_access=True)
        self.assertNotEqual(resp.status_code, 404,
                            f"Dono legítimo não deve receber 404 (got {resp.status_code})")
        self.assertEqual(resp.status_code, 200)

    def test_superuser_ve_qualquer_loja(self):
        """Superuser não deve ser bloqueado."""
        resp = self._call(_superuser(), store=_fake_store(), can_access=True)
        self.assertEqual(resp.status_code, 200)
