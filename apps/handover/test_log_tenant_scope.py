"""Regressão P1: HandoverLogViewSet.get_queryset() quebrava com FieldError.

A query original `conversation__store__members=user` é inválida:
- `Conversation` tem `account` (FK → WhatsAppAccount), não `store`.
- `Store` não tem campo `members` (tem `staff` M2M e `owner` FK).

Para qualquer não-superuser, o endpoint `GET /handover/logs/` lançava
`FieldError: Cannot resolve keyword 'store'…` → 500.

O fix substitui por `conversation__account_id__in=accessible_whatsapp_account_ids(user)`,
alinhado com o padrão do projeto (HandoverViewSet.get_conversation usa a mesma função).
"""

import inspect
from unittest import TestCase
from unittest.mock import MagicMock, patch, call


class HandoverLogViewSetGetQuerysetFieldPathTest(TestCase):
    """Verifica que get_queryset usa o caminho de campo correto."""

    def _get_source(self):
        import apps.handover.views as views_module
        return inspect.getsource(views_module.HandoverLogViewSet.get_queryset)

    def test_source_does_not_use_store_path(self):
        """conversation__store não existe em Conversation — query antiga causava FieldError."""
        src = self._get_source()
        self.assertNotIn("conversation__store", src,
                         "get_queryset usa conversation__store que não existe no modelo Conversation")

    def test_source_does_not_use_members_field(self):
        """Store não tem campo members — path inválido."""
        src = self._get_source()
        self.assertNotIn("__members", src,
                         "get_queryset usa __members que não existe em Store")

    def test_source_uses_account_id_scope(self):
        """Fix correto: filtrar por conversation__account_id__in (account é o campo real)."""
        src = self._get_source()
        self.assertIn("account_id", src,
                      "get_queryset deve usar conversation__account_id__in para escopar por tenant")

    def test_source_uses_accessible_account_ids(self):
        """Fix correto: usa accessible_whatsapp_account_ids — mesma função do HandoverViewSet."""
        src = self._get_source()
        self.assertIn("accessible_whatsapp_account_ids", src,
                      "get_queryset deve usar accessible_whatsapp_account_ids para isolar por tenant")

    def test_superuser_bypass_present(self):
        """Superuser continua vendo todos os logs (comportamento correto mantido)."""
        src = self._get_source()
        self.assertIn("is_superuser", src,
                      "get_queryset deve manter bypass de superuser")


class HandoverLogViewSetGetQuerysetLogicTest(TestCase):
    """Verifica o comportamento do get_queryset via mock — sem banco."""

    def _make_viewset(self, user):
        from apps.handover.views import HandoverLogViewSet
        viewset = HandoverLogViewSet()
        request = MagicMock()
        request.user = user
        viewset.request = request
        return viewset

    def _mock_user(self, is_superuser=False, pk=99):
        user = MagicMock()
        user.is_superuser = is_superuser
        user.pk = pk
        user.id = pk
        return user

    def test_superuser_gets_all_logs(self):
        """Superuser → HandoverLog.objects.all() sem filtro."""
        user = self._mock_user(is_superuser=True)
        viewset = self._make_viewset(user)

        with patch("apps.handover.views.HandoverLog") as mock_model:
            mock_model.objects.all.return_value = MagicMock()
            result = viewset.get_queryset()
            mock_model.objects.all.assert_called_once()

    def test_non_superuser_scopes_by_account(self):
        """Não-superuser → filtra por conversation__account_id__in."""
        user = self._mock_user(is_superuser=False)
        viewset = self._make_viewset(user)

        fake_ids = [1, 2, 3]

        with patch("apps.handover.views.HandoverLog") as mock_model, \
             patch("apps.core.permissions.accessible_whatsapp_account_ids",
                   return_value=fake_ids) as mock_ids:
            mock_qs = MagicMock()
            mock_model.objects.filter.return_value = mock_qs
            viewset.get_queryset()
            mock_model.objects.filter.assert_called_once_with(
                conversation__account_id__in=fake_ids
            )

    def test_non_superuser_does_not_call_all(self):
        """Não-superuser não vê todos os logs (sem bypass cross-tenant)."""
        user = self._mock_user(is_superuser=False)
        viewset = self._make_viewset(user)

        fake_ids = []

        with patch("apps.handover.views.HandoverLog") as mock_model, \
             patch("apps.core.permissions.accessible_whatsapp_account_ids",
                   return_value=fake_ids):
            mock_model.objects.filter.return_value = MagicMock()
            viewset.get_queryset()
            mock_model.objects.all.assert_not_called()

    def test_no_field_error_for_non_superuser(self):
        """get_queryset NÃO deve levantar AttributeError/FieldError por path inválido."""
        user = self._mock_user(is_superuser=False)
        viewset = self._make_viewset(user)

        with patch("apps.handover.views.HandoverLog") as mock_model, \
             patch("apps.core.permissions.accessible_whatsapp_account_ids",
                   return_value=[]):
            mock_model.objects.filter.return_value = MagicMock()
            try:
                viewset.get_queryset()
            except (AttributeError, TypeError) as exc:
                self.fail(f"get_queryset levantou {type(exc).__name__}: {exc}")
