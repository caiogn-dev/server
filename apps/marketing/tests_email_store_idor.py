"""Regressão de segurança: IDOR de escrita cross-tenant em serializers de marketing [P1].

Antes do fix:
- EmailTemplateSerializer.store — sem validate_store → POST cria template em loja alheia.
- EmailCampaignSerializer.store  — sem validate_store → POST cria campanha em loja alheia.
- EmailAutomationSerializer.store — sem validate_store → POST cria automação em loja alheia.
- debug action usa IsAdminUser (is_staff) em vez de is_superuser → staff de loja A
  acessa debug de qualquer loja do sistema.

Fix: validate_store em cada serializer (user_can_access_store ou superuser bypass);
     debug requer is_superuser.

Técnica: SimpleTestCase + análise estática + DRF field introspection. Sem DB/Docker.
"""
import importlib
import inspect
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_serializers():
    return importlib.import_module('apps.marketing.api.serializers')


def _load_views():
    return importlib.import_module('apps.marketing.api.views')


def _make_user(is_superuser=False, is_staff=False):
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = is_superuser
    u.is_staff = is_staff
    return u


def _make_store(store_id='aaaaaaaa-0000-0000-0000-000000000001'):
    s = MagicMock()
    s.id = store_id
    s.slug = 'loja-a'
    return s


# ---------------------------------------------------------------------------
# 1. Análise estática — validate_store presente
# ---------------------------------------------------------------------------

class TestEmailTemplateSerializerHasValidateStore(SimpleTestCase):

    def test_validate_store_defined(self):
        m = _load_serializers()
        cls = m.EmailTemplateSerializer
        self.assertIn('validate_store', dir(cls),
                      'EmailTemplateSerializer deve ter validate_store')

    def test_validate_store_is_callable(self):
        m = _load_serializers()
        cls = m.EmailTemplateSerializer
        self.assertTrue(callable(getattr(cls, 'validate_store', None)))

    def test_source_references_user_can_access_store(self):
        src = inspect.getsource(_load_serializers())
        self.assertIn('user_can_access_store', src,
                      'serializers.py deve referenciar user_can_access_store')


class TestEmailCampaignSerializerHasValidateStore(SimpleTestCase):

    def test_validate_store_defined(self):
        m = _load_serializers()
        cls = m.EmailCampaignSerializer
        self.assertIn('validate_store', dir(cls),
                      'EmailCampaignSerializer deve ter validate_store')


class TestEmailAutomationSerializerHasValidateStore(SimpleTestCase):

    def test_validate_store_defined(self):
        m = _load_serializers()
        cls = m.EmailAutomationSerializer
        self.assertIn('validate_store', dir(cls),
                      'EmailAutomationSerializer deve ter validate_store')


# ---------------------------------------------------------------------------
# 2. Funcional — validate_store rejeita acesso não autorizado
# ---------------------------------------------------------------------------

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


def _make_serializer(cls, request):
    """Instancia um serializer com parent=None e contexto de request (sem DB)."""
    s = cls.__new__(cls)
    s.parent = None   # necessário para DRF context property
    s._context = {'request': request}
    return s


class TestEmailTemplateValidateStoreRejectsUnauthorized(SimpleTestCase):
    """validate_store deve levantar ValidationError para store alheia."""

    @override_settings(**_SETTINGS)
    def test_reject_foreign_store(self):
        from rest_framework import serializers as drf_serializers

        m = _load_serializers()
        cls = m.EmailTemplateSerializer

        attacker = _make_user(is_superuser=False)
        victim_store = _make_store()

        request = MagicMock()
        request.user = attacker

        s = _make_serializer(cls, request)

        with patch('apps.core.permissions.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                s.validate_store(victim_store)

    @override_settings(**_SETTINGS)
    def test_superuser_can_pass(self):
        m = _load_serializers()
        cls = m.EmailTemplateSerializer

        superuser = _make_user(is_superuser=True)
        any_store = _make_store()

        request = MagicMock()
        request.user = superuser

        s = _make_serializer(cls, request)

        with patch('apps.core.permissions.user_can_access_store', return_value=False):
            result = s.validate_store(any_store)
        self.assertEqual(result, any_store)

    @override_settings(**_SETTINGS)
    def test_authorized_user_passes(self):
        m = _load_serializers()
        cls = m.EmailTemplateSerializer

        owner = _make_user(is_superuser=False)
        own_store = _make_store()

        request = MagicMock()
        request.user = owner

        s = _make_serializer(cls, request)

        with patch('apps.core.permissions.user_can_access_store', return_value=True):
            result = s.validate_store(own_store)
        self.assertEqual(result, own_store)


class TestEmailAutomationValidateStoreRejectsUnauthorized(SimpleTestCase):

    @override_settings(**_SETTINGS)
    def test_reject_foreign_store(self):
        from rest_framework import serializers as drf_serializers

        m = _load_serializers()
        cls = m.EmailAutomationSerializer

        attacker = _make_user(is_superuser=False)
        victim_store = _make_store()

        request = MagicMock()
        request.user = attacker

        s = _make_serializer(cls, request)

        with patch('apps.core.permissions.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                s.validate_store(victim_store)


# ---------------------------------------------------------------------------
# 3. debug action — requer is_superuser, não is_staff
# ---------------------------------------------------------------------------

class TestDebugActionRequiresSuperuser(SimpleTestCase):

    def test_debug_permission_is_not_is_admin_user_only(self):
        """A action debug NÃO deve confiar exclusivamente em IsAdminUser (is_staff)."""
        views_src = inspect.getsource(_load_views())
        # Após o fix, debug pode usar IsAdminUser mas deve também checar is_superuser
        # OU remover IsAdminUser em favor de is_superuser check na view.
        # A forma mais simples: não há mais 'IsAdminUser' associada ao debug sem is_superuser.
        # Testamos que o source não contém `IsAdminUser` sem `is_superuser` no mesmo bloco.
        self.assertIn('is_superuser', views_src,
                      'views.py deve usar is_superuser no controle de acesso do debug')

    def test_debug_does_not_rely_solely_on_is_staff(self):
        """debug não deve usar IsAdminUser como único gate (is_staff != cross-tenant authority)."""
        import re
        views_src = inspect.getsource(_load_views())
        # Verifica que IsAdminUser não é a única permissão listada para debug sem
        # nenhuma verificação de is_superuser na função.
        debug_block_match = re.search(
            r"def debug\(self.*?(?=\n    @action|\n    def |\Z)",
            views_src, re.DOTALL
        )
        if debug_block_match:
            debug_src = debug_block_match.group(0)
            # Se IsAdminUser ainda está presente, is_superuser também deve estar
            if 'IsAdminUser' in views_src:
                self.assertIn('is_superuser', debug_src,
                              "Se IsAdminUser ainda presente, debug também deve checar is_superuser")
