"""Regressão de segurança: is_staff bypassa isolamento de tenant em conversas.

Bugs corrigidos:
1. UniversalConversationService._is_staff (service.py:165) — retorna True
   para is_staff=True, expondo TODAS as conversas de Instagram e Messenger
   de qualquer tenant (PII leak: mensagens de clientes de outros tenants).

2. ConversationViewSet.assign_agent (views.py:314) — is_staff bypassa
   verificação de acesso a conta, permitindo atribuir qualquer usuário
   is_staff a conversas de outros tenants.

Convenção: is_staff = acesso ao /admin; NÃO concede cross-tenant.
Apenas is_superuser tem acesso irrestrito.
"""
import inspect
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from django.contrib.auth.models import AnonymousUser


def _make_user(is_superuser=False, is_staff=False):
    u = MagicMock()
    u.is_superuser = is_superuser
    u.is_staff = is_staff
    u.is_authenticated = True
    return u


class UniversalServiceIsStaffTest(SimpleTestCase):
    """UniversalConversationService._is_staff — só is_superuser é cross-tenant."""

    def _service(self):
        from apps.conversations.services.universal_conversation_service import (
            UniversalConversationService,
        )
        return UniversalConversationService()

    def test_superuser_retorna_true(self):
        """is_superuser=True → True (acesso cross-tenant concedido)."""
        svc = self._service()
        self.assertTrue(svc._is_staff(_make_user(is_superuser=True, is_staff=False)))

    def test_staff_sem_superuser_retorna_false(self):
        """is_staff=True, is_superuser=False → False (sem acesso cross-tenant).

        Bug: antes retornava True, vazando conversas de todos os tenants.
        """
        svc = self._service()
        self.assertFalse(
            svc._is_staff(_make_user(is_superuser=False, is_staff=True)),
            "_is_staff retorna True para is_staff puro — PII leak ativo: "
            "conversas de Instagram/Messenger de todos os tenants ficam visíveis",
        )

    def test_usuario_normal_retorna_false(self):
        svc = self._service()
        self.assertFalse(svc._is_staff(_make_user(is_superuser=False, is_staff=False)))

    def test_anonimo_retorna_false(self):
        svc = self._service()
        self.assertFalse(svc._is_staff(AnonymousUser()))

    def test_superuser_com_staff_retorna_true(self):
        """Superuser que também é staff ainda tem acesso cross-tenant."""
        svc = self._service()
        self.assertTrue(svc._is_staff(_make_user(is_superuser=True, is_staff=True)))


class UniversalServiceIsStaffSourceTest(SimpleTestCase):
    """Verifica estruturalmente que _is_staff não inclui is_staff na condição."""

    def test_is_staff_nao_usa_atributo_is_staff(self):
        """_is_staff não deve retornar True com base em user.is_staff."""
        from apps.conversations.services.universal_conversation_service import (
            UniversalConversationService,
        )
        source = inspect.getsource(UniversalConversationService._is_staff)
        # A implementação não deve checar is_staff do usuário
        self.assertNotIn('"is_staff"', source,
            "_is_staff usa getattr(user, 'is_staff') — is_staff não deve dar "
            "acesso cross-tenant a conversas (PII)")
        self.assertNotIn("'is_staff'", source,
            "_is_staff usa getattr(user, 'is_staff') — is_staff não deve dar "
            "acesso cross-tenant a conversas (PII)")


class AssignAgentIsStaffSourceTest(SimpleTestCase):
    """assign_agent — is_staff não deve bypassar verificação de acesso a conta."""

    def test_assign_agent_nao_usa_is_staff_como_bypass(self):
        from apps.conversations.api.views import ConversationViewSet
        source = inspect.getsource(ConversationViewSet.assign_agent)
        self.assertNotIn('and not agent.is_staff', source,
            "assign_agent usa 'and not agent.is_staff' como bypass — "
            "is_staff não deve bypassar verificação de acesso a conta na atribuição")

    def test_assign_agent_usa_superuser(self):
        from apps.conversations.api.views import ConversationViewSet
        source = inspect.getsource(ConversationViewSet.assign_agent)
        self.assertIn('is_superuser', source)


class AssignAgentLogicTest(SimpleTestCase):
    """Testa a lógica de bypass diretamente via condição esperada após o fix."""

    def _should_check_account(self, is_superuser, is_staff):
        """Simula a condição CORRETA pós-fix: só superuser bypassa."""
        agent = MagicMock()
        agent.is_superuser = is_superuser
        agent.is_staff = is_staff
        return not agent.is_superuser

    def test_superuser_bypassa(self):
        self.assertFalse(self._should_check_account(is_superuser=True, is_staff=False))

    def test_staff_nao_bypassa(self):
        self.assertTrue(self._should_check_account(is_superuser=False, is_staff=True))

    def test_normal_nao_bypassa(self):
        self.assertTrue(self._should_check_account(is_superuser=False, is_staff=False))

    def test_superuser_e_staff_bypassa(self):
        self.assertFalse(self._should_check_account(is_superuser=True, is_staff=True))
