"""Regressão de segurança — IDOR de escrita em serializers (continuação Onda 2).

Cobre três serializers que expõem o campo `store` como writable sem
validate_store, permitindo que um usuário autenticado crie/edite registros
em lojas de outros tenants.

Vulnerabilidades:
  1. StoreIntegrationCreateSerializer — POST /api/v1/stores/{slug}/integrations/
     Vetor: passa store=<UUID-de-loja-alheia> no body e cria integração em
     outro tenant mesmo tendo permissão apenas na loja da URL.

  2. StoreWebhookSerializer — POST /api/v1/stores/{slug}/webhooks/
     Mesmo vetor para criação de webhooks.

  3. StorePrintAgentCreateSerializer — POST /api/v1/stores/{slug}/print-agents/
     Mesmo vetor para criação de print agents.

Todos os testes usam SimpleTestCase + mocks (sem banco, sem migrations).
"""
import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework import serializers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(is_authenticated=True, is_superuser=False):
    u = Mock()
    u.is_authenticated = is_authenticated
    u.is_superuser = is_superuser
    return u


def _request(user):
    r = Mock()
    r.user = user
    return r


def _store():
    s = Mock()
    s.id = uuid.uuid4()
    return s


_VALIDATE_STORE_PATH = 'apps.core.permissions.user_can_access_store'


# ---------------------------------------------------------------------------
# 1. StoreIntegrationCreateSerializer
# ---------------------------------------------------------------------------

class StoreIntegrationCreateSerializerIDORTest(SimpleTestCase):

    def _make_serializer(self, user):
        from apps.stores.api.serializers import StoreIntegrationCreateSerializer
        s = StoreIntegrationCreateSerializer()
        s._context = {'request': _request(user)}
        return s

    def test_rejeita_store_de_outro_tenant(self):
        """Usuário sem acesso à loja recebe ValidationError (info-hiding)."""
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=False):
            with self.assertRaises(serializers.ValidationError) as ctx:
                ser.validate_store(store)
        self.assertIn('não encontrada', str(ctx.exception.detail).lower())

    def test_aceita_store_propria(self):
        """Usuário com acesso à loja recebe o objeto sem erro."""
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=True):
            result = ser.validate_store(store)
        self.assertEqual(result, store)

    def test_superuser_bypassa_check(self):
        """Superuser pode usar qualquer store sem verificação de tenant."""
        ser = self._make_serializer(_user(is_superuser=True))
        store = _store()
        with patch(_VALIDATE_STORE_PATH) as mock_check:
            result = ser.validate_store(store)
        mock_check.assert_not_called()
        self.assertEqual(result, store)

    def test_sem_request_no_contexto_nao_explode(self):
        """Sem request no contexto o check é pulado — a view garante auth."""
        from apps.stores.api.serializers import StoreIntegrationCreateSerializer
        ser = StoreIntegrationCreateSerializer()
        ser._context = {}
        store = _store()
        result = ser.validate_store(store)
        self.assertEqual(result, store)


# ---------------------------------------------------------------------------
# 2. StoreWebhookSerializer
# ---------------------------------------------------------------------------

class StoreWebhookSerializerIDORTest(SimpleTestCase):

    def _make_serializer(self, user):
        from apps.stores.api.serializers import StoreWebhookSerializer
        s = StoreWebhookSerializer()
        s._context = {'request': _request(user)}
        return s

    def test_rejeita_store_de_outro_tenant(self):
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=False):
            with self.assertRaises(serializers.ValidationError) as ctx:
                ser.validate_store(store)
        self.assertIn('não encontrada', str(ctx.exception.detail).lower())

    def test_aceita_store_propria(self):
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=True):
            result = ser.validate_store(store)
        self.assertEqual(result, store)

    def test_superuser_bypassa_check(self):
        ser = self._make_serializer(_user(is_superuser=True))
        store = _store()
        with patch(_VALIDATE_STORE_PATH) as mock_check:
            result = ser.validate_store(store)
        mock_check.assert_not_called()
        self.assertEqual(result, store)

    def test_sem_request_no_contexto_nao_explode(self):
        from apps.stores.api.serializers import StoreWebhookSerializer
        ser = StoreWebhookSerializer()
        ser._context = {}
        store = _store()
        result = ser.validate_store(store)
        self.assertEqual(result, store)


# ---------------------------------------------------------------------------
# 3. StorePrintAgentCreateSerializer
# ---------------------------------------------------------------------------

class StorePrintAgentCreateSerializerIDORTest(SimpleTestCase):

    def _make_serializer(self, user):
        from apps.stores.api.serializers import StorePrintAgentCreateSerializer
        s = StorePrintAgentCreateSerializer()
        s._context = {'request': _request(user)}
        return s

    def test_rejeita_store_de_outro_tenant(self):
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=False):
            with self.assertRaises(serializers.ValidationError) as ctx:
                ser.validate_store(store)
        self.assertIn('não encontrada', str(ctx.exception.detail).lower())

    def test_aceita_store_propria(self):
        ser = self._make_serializer(_user(is_superuser=False))
        store = _store()
        with patch(_VALIDATE_STORE_PATH, return_value=True):
            result = ser.validate_store(store)
        self.assertEqual(result, store)

    def test_superuser_bypassa_check(self):
        ser = self._make_serializer(_user(is_superuser=True))
        store = _store()
        with patch(_VALIDATE_STORE_PATH) as mock_check:
            result = ser.validate_store(store)
        mock_check.assert_not_called()
        self.assertEqual(result, store)

    def test_sem_request_no_contexto_nao_explode(self):
        from apps.stores.api.serializers import StorePrintAgentCreateSerializer
        ser = StorePrintAgentCreateSerializer()
        ser._context = {}
        store = _store()
        result = ser.validate_store(store)
        self.assertEqual(result, store)


# ---------------------------------------------------------------------------
# 4. Verificação estática: nenhum dos três contém is_staff no guard de tenant
# ---------------------------------------------------------------------------

class NoIsStaffInValidateStoreTest(SimpleTestCase):
    """Garante que os novos validate_store usam is_superuser, não is_staff."""

    def _get_source(self):
        import inspect
        import apps.stores.api.serializers as mod
        return inspect.getsource(mod)

    def _get_validate_store_blocks(self, serializer_class_name):
        import importlib
        import inspect
        mod = importlib.import_module('apps.stores.api.serializers')
        cls = getattr(mod, serializer_class_name)
        fn = getattr(cls, 'validate_store', None)
        self.assertIsNotNone(fn, f'{serializer_class_name} deve ter validate_store')
        return inspect.getsource(fn)

    def test_integration_validate_store_usa_is_superuser(self):
        src = self._get_validate_store_blocks('StoreIntegrationCreateSerializer')
        self.assertIn('is_superuser', src)
        self.assertNotIn('is_staff', src)

    def test_webhook_validate_store_usa_is_superuser(self):
        src = self._get_validate_store_blocks('StoreWebhookSerializer')
        self.assertIn('is_superuser', src)
        self.assertNotIn('is_staff', src)

    def test_print_agent_validate_store_usa_is_superuser(self):
        src = self._get_validate_store_blocks('StorePrintAgentCreateSerializer')
        self.assertIn('is_superuser', src)
        self.assertNotIn('is_staff', src)
