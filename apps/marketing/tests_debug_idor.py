"""Regressão de segurança: IDOR no debug action de CustomersViewSet [P1].

Antes do fix:
- debug action usava IsAdminUser (is_staff) sem _user_can_use_store.
- Qualquer is_staff=True podia ler PII (email, first_name, last_name, date_joined)
  de até 5 clientes de QUALQUER loja passando store_id arbitrário.

Fix: substitui IsAdminUser por gate _user_can_use_store equivalente ao usado em
MarketingStatsViewSet.list — apenas is_superuser ou proprietário da loja podem
acessar; is_staff sem vínculo de loja recebe 403.

Técnica: SimpleTestCase + mocks. Sem Docker/PostgreSQL.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
_VIEW_MODULE = 'apps.marketing.api.views'


def _user(is_superuser=False, is_staff=False, store_ids=None):
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = is_superuser
    u.is_staff = is_staff
    u.id = uuid4()
    u._store_ids = store_ids or []
    return u


def _make_view():
    from apps.marketing.api.views import CustomersViewSet
    return CustomersViewSet.as_view({'get': 'debug'})


def _call(user, store_id, can_use_store=False):
    """Chama debug com _force_auth_user (padrão dos testes de marketing)."""
    req = factory.get('/debug/', {'store': str(store_id)})
    req._force_auth_user = user
    with patch(f'{_VIEW_MODULE}._user_can_use_store', return_value=can_use_store):
        return _make_view()(req)


@override_settings(**_SETTINGS)
class TestDebugIdorGate(SimpleTestCase):
    """Gate de tenant: is_staff sem acesso à loja não pode ler PII."""

    def test_staff_sem_loja_recebe_403(self):
        """is_staff=True sem vínculo de loja → 403 (antes retornava 200 com PII)."""
        user = _user(is_staff=True, is_superuser=False)
        resp = _call(user, store_id=uuid4(), can_use_store=False)
        self.assertEqual(resp.status_code, 403)

    def test_usuario_autenticado_sem_loja_recebe_403(self):
        """Usuário autenticado sem vínculo de loja → 403."""
        user = _user(is_staff=False, is_superuser=False)
        resp = _call(user, store_id=uuid4(), can_use_store=False)
        self.assertEqual(resp.status_code, 403)

    def test_store_param_ausente_recebe_400(self):
        """store param ausente → 400 antes mesmo do tenant check."""
        user = _user(is_superuser=True)
        req = factory.get('/debug/')
        req._force_auth_user = user
        with patch(f'{_VIEW_MODULE}._user_can_use_store', return_value=True):
            resp = _make_view()(req)
        self.assertEqual(resp.status_code, 400)

    def test_nenhum_pii_vazado_sem_acesso(self):
        """403 não expõe PII no corpo da resposta."""
        user = _user(is_staff=False)
        resp = _call(user, store_id=uuid4(), can_use_store=False)
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn('email', str(resp.data))
        self.assertNotIn('first_name', str(resp.data))
        self.assertNotIn('sample', str(resp.data))
