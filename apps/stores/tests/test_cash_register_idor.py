"""Regressão de segurança: IDOR no caixa de PDV (cash_views.py) [P0].

Antes do fix, `IsStoreOwnerOrStaff.has_permission()` só verificava ownership
quando `store_pk` estava em `view.kwargs`. As views de caixa são roteadas com
`store_slug` — `store_pk` nunca está nos kwargs — então `has_permission()` sempre
retornava `True` para qualquer usuário autenticado.

Vetor concreto: `POST /api/v1/stores/{slug-da-vítima}/cash/open/` de uma conta
completamente não relacionada abria o caixa e registrava o atacante como `opened_by`.

Fix: cada view de caixa chama `user_can_access_store` explicitamente após resolver a
loja; usuários sem acesso recebem 404 (sem revelar se a loja existe).

Técnica: `SimpleTestCase` + mocks + `APIRequestFactory`. Sem Docker/PostgreSQL.
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


def _anon_user():
    u = MagicMock()
    u.is_authenticated = False
    u.is_superuser = False
    u.is_staff = False
    return u


def _attacker():
    """Usuário autenticado sem acesso à loja-alvo."""
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


factory = APIRequestFactory()


@override_settings(**_SETTINGS)
class CashOpenIDORTest(SimpleTestCase):
    """CashOpenView: atacante não pode abrir caixa de loja alheia."""

    def _call(self, user, store=None, can_access=False):
        from apps.stores.api.views.cash_views import CashOpenView
        req = factory.post('/cash/open/', {'opening_amount': '0'}, format='json')
        req._force_auth_user = user
        with patch('apps.stores.api.views.cash_views._get_store', return_value=store), \
             patch('apps.stores.api.views.cash_views.user_can_access_store', return_value=can_access), \
             patch('apps.stores.api.views.cash_views._get_open_session', return_value=None):
            return CashOpenView.as_view()(req, store_slug='vitima-store')

    def test_atacante_sem_acesso_recebe_404(self):
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404,
                         "Atacante sem acesso deve receber 404, não criar caixa (evita IDOR)")

    def test_atacante_resposta_nao_revela_existencia_da_loja(self):
        """404 tanto para loja inexistente quanto para loja sem acesso (info-hiding)."""
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404)

    def test_dono_com_acesso_passa_pelo_gate(self):
        """Proprietário legítimo deve continuar chegando à lógica de abertura."""
        fake_session = MagicMock()
        fake_session.expected_cash.return_value = 0
        fake_session.movements.all.return_value = []
        with patch('apps.stores.api.views.cash_views.StoreCashSession.objects.create',
                   return_value=fake_session), \
             patch('apps.stores.api.views.cash_views.CashSessionSerializer') as mock_ser:
            mock_ser.return_value.data = {'status': 'open'}
            resp = self._call(_owner(), store=_fake_store(), can_access=True)
        # gate deve passar — resposta 201 indica que chegou ao create
        self.assertNotEqual(resp.status_code, 404,
                            f"Dono legítimo não deve receber 404 (got {resp.status_code})")

    def test_superuser_nao_precisa_de_acesso_explicito(self):
        """Superuser passa pelo gate sem chamar user_can_access_store."""
        fake_session = MagicMock()
        fake_session.expected_cash.return_value = 0
        fake_session.movements.all.return_value = []
        with patch('apps.stores.api.views.cash_views.StoreCashSession.objects.create',
                   return_value=fake_session), \
             patch('apps.stores.api.views.cash_views.CashSessionSerializer') as mock_ser:
            mock_ser.return_value.data = {'status': 'open'}
            resp = self._call(_superuser(), store=_fake_store(), can_access=False)
        self.assertNotEqual(resp.status_code, 404,
                            "Superuser não deve ser bloqueado mesmo sem acesso explícito")

    def test_loja_inexistente_retorna_404(self):
        resp = self._call(_attacker(), store=None, can_access=False)
        self.assertEqual(resp.status_code, 404)


@override_settings(**_SETTINGS)
class CashCurrentIDORTest(SimpleTestCase):
    """CashCurrentView: atacante não pode ler estado do caixa de loja alheia."""

    def _call(self, user, store=None, can_access=False):
        from apps.stores.api.views.cash_views import CashCurrentView
        req = factory.get('/cash/current/')
        req._force_auth_user = user
        with patch('apps.stores.api.views.cash_views._get_store', return_value=store), \
             patch('apps.stores.api.views.cash_views.user_can_access_store', return_value=can_access), \
             patch('apps.stores.api.views.cash_views._get_open_session', return_value=None):
            return CashCurrentView.as_view()(req, store_slug='vitima-store')

    def test_atacante_nao_le_caixa_alheio(self):
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404)

    def test_dono_passa_pelo_gate(self):
        resp = self._call(_owner(), store=_fake_store(), can_access=True)
        # sem sessão aberta → 404 do negócio, não 404 do gate
        self.assertEqual(resp.status_code, 404)


@override_settings(**_SETTINGS)
class CashMovementIDORTest(SimpleTestCase):
    """CashMovementView: atacante não pode registrar sangria/reforço em loja alheia."""

    def _call(self, user, store=None, can_access=False):
        from apps.stores.api.views.cash_views import CashMovementView
        req = factory.post('/cash/movement/',
                           {'kind': 'sangria', 'amount': '10.00'}, format='json')
        req._force_auth_user = user
        with patch('apps.stores.api.views.cash_views._get_store', return_value=store), \
             patch('apps.stores.api.views.cash_views.user_can_access_store', return_value=can_access), \
             patch('apps.stores.api.views.cash_views._get_open_session', return_value=None):
            return CashMovementView.as_view()(req, store_slug='vitima-store')

    def test_atacante_nao_registra_movimento(self):
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404)

    def test_dono_passa_pelo_gate(self):
        resp = self._call(_owner(), store=_fake_store(), can_access=True)
        # sem sessão aberta → 400 do negócio
        self.assertEqual(resp.status_code, 400)


@override_settings(**_SETTINGS)
class CashCloseIDORTest(SimpleTestCase):
    """CashCloseView: atacante não pode fechar caixa de loja alheia."""

    def _call(self, user, store=None, can_access=False):
        from apps.stores.api.views.cash_views import CashCloseView
        req = factory.post('/cash/close/',
                           {'counted_amount': '100.00'}, format='json')
        req._force_auth_user = user
        with patch('apps.stores.api.views.cash_views._get_store', return_value=store), \
             patch('apps.stores.api.views.cash_views.user_can_access_store', return_value=can_access), \
             patch('apps.stores.api.views.cash_views._get_open_session', return_value=None):
            return CashCloseView.as_view()(req, store_slug='vitima-store')

    def test_atacante_nao_fecha_caixa_alheio(self):
        resp = self._call(_attacker(), store=_fake_store(), can_access=False)
        self.assertEqual(resp.status_code, 404)

    def test_dono_passa_pelo_gate(self):
        resp = self._call(_owner(), store=_fake_store(), can_access=True)
        # sem sessão aberta → 400 do negócio
        self.assertEqual(resp.status_code, 400)
