"""Regressão de segurança: IDOR cross-tenant em AgentFlow e AutoMessage.

1. CreateAgentFlowSerializer — campo `store` writable sem validate_store.
   Vetor: POST /api/v1/automation/flows/ com {"store": "<loja_alheia_uuid>", ...}
   cria um AgentFlow no tenant da vítima.

2. AutoMessageViewSet.create — is_staff bypassa o check de tenant (P1).
   Vetor: usuário com is_staff=True POST /api/v1/automation/auto-messages/ com
   {"company_id": "<company_de_outro_tenant>"} tem acesso concedido indevidamente.
   Convenção do projeto: apenas is_superuser tem acesso cross-tenant irrestrito.
"""
import inspect
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Helpers de mock compartilhados
# ---------------------------------------------------------------------------

def _make_store(owned=True, user=None):
    store = MagicMock()
    store.id = 'aaaa-1111'
    store.owner_id = user.id if user and owned else 'other-owner-id'
    store.staff.filter.return_value.exists.return_value = False
    return store


def _make_user(is_superuser=False, is_staff=False, uid='user-id-1'):
    user = MagicMock()
    user.id = uid
    user.is_superuser = is_superuser
    user.is_staff = is_staff
    user.is_authenticated = True
    return user


def _make_request(user):
    req = MagicMock()
    req.user = user
    return req


# ---------------------------------------------------------------------------
# 1. CreateAgentFlowSerializer.validate_store
# ---------------------------------------------------------------------------

class CreateAgentFlowSerializerValidateStoreTest(SimpleTestCase):
    """Testa que validate_store bloqueia acesso cross-tenant."""

    def _get_serializer(self, request=None):
        from apps.automation.api.serializers import CreateAgentFlowSerializer
        context = {'request': request} if request else {}
        s = CreateAgentFlowSerializer.__new__(CreateAgentFlowSerializer)
        s.parent = None
        s._context = context
        return s

    def test_validate_store_existe(self):
        """CreateAgentFlowSerializer deve ter o método validate_store."""
        from apps.automation.api.serializers import CreateAgentFlowSerializer
        self.assertTrue(
            hasattr(CreateAgentFlowSerializer, 'validate_store'),
            'CreateAgentFlowSerializer deve ter validate_store para bloquear IDOR cross-tenant.',
        )

    def test_rejeita_store_de_outro_tenant(self):
        """Usuário não-superuser não pode criar AgentFlow em loja alheia."""
        from apps.automation.api.serializers import CreateAgentFlowSerializer
        from rest_framework import serializers as drf_serializers

        user = _make_user()
        store = _make_store(owned=False)
        request = _make_request(user)
        s = self._get_serializer(request)

        with patch('apps.core.permissions.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                s.validate_store(store)

    def test_aceita_store_propria(self):
        """Usuário pode criar AgentFlow em loja que tem acesso."""
        from apps.automation.api.serializers import CreateAgentFlowSerializer

        user = _make_user()
        store = _make_store(owned=True, user=user)
        request = _make_request(user)
        s = self._get_serializer(request)

        with patch('apps.core.permissions.user_can_access_store', return_value=True):
            result = s.validate_store(store)
        self.assertEqual(result, store)

    def test_superuser_bypassa_check(self):
        """Superuser pode criar AgentFlow em qualquer loja."""
        from apps.automation.api.serializers import CreateAgentFlowSerializer

        user = _make_user(is_superuser=True)
        store = _make_store(owned=False)
        request = _make_request(user)
        s = self._get_serializer(request)

        # user_can_access_store NÃO deve ser chamado — superuser sempre passa
        with patch('apps.core.permissions.user_can_access_store') as mock_check:
            result = s.validate_store(store)
        mock_check.assert_not_called()
        self.assertEqual(result, store)

    def test_sem_request_no_contexto_nao_explode(self):
        """Sem contexto de request, validate_store deve retornar o valor sem erro."""
        from apps.automation.api.serializers import CreateAgentFlowSerializer

        store = _make_store()
        s = self._get_serializer(request=None)
        result = s.validate_store(store)
        self.assertEqual(result, store)

    def test_validate_store_usa_is_superuser(self):
        """validate_store deve usar is_superuser (não is_staff) como bypass cross-tenant."""
        from apps.automation.api import serializers as mod
        src = inspect.getsource(
            mod.CreateAgentFlowSerializer.validate_store  # noqa: WPS219
        )
        self.assertIn('is_superuser', src)
        self.assertNotIn('is_staff', src)


# ---------------------------------------------------------------------------
# 2. AutoMessageViewSet.create — is_staff não bypassa tenant check
# ---------------------------------------------------------------------------

class AutoMessageViewSetIsStaffTest(SimpleTestCase):
    """Testa que is_staff NÃO bypassa o check de tenant em AutoMessageViewSet.create."""

    def test_create_nao_usa_is_staff_para_bypass(self):
        """is_staff não deve ser condição suficiente para acesso cross-tenant."""
        from apps.automation.api.views import auto_message_views as mod
        src = inspect.getsource(mod.AutoMessageViewSet.create)
        # O guard deve ser apenas is_superuser — is_staff não deve aparecer
        # como bypass no check de tenant da criação de AutoMessage.
        self.assertNotIn(
            'is_staff',
            src,
            'AutoMessageViewSet.create não deve usar is_staff como bypass de tenant. '
            'Apenas is_superuser concede acesso cross-tenant (convenção do projeto).',
        )

    def test_create_usa_is_superuser(self):
        """O check de tenant deve usar is_superuser."""
        from apps.automation.api.views import auto_message_views as mod
        src = inspect.getsource(mod.AutoMessageViewSet.create)
        self.assertIn('is_superuser', src)
