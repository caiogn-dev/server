"""Garante que AuditLogViewSet exige superuser — não apenas is_staff.

AuditLog armazena user_email, user_ip, old_values/new_values de todos os
tenants. Protegê-lo com IsAdminUser (is_staff) permitia que qualquer
usuário staff lesse logs cross-tenant. A correção substitui por IsSuperUser.

Sem dependência de banco; usa mocks de DRF.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


def _make_user(is_superuser=False, is_staff=False, authenticated=True):
    user = MagicMock()
    user.is_authenticated = authenticated
    user.is_superuser = is_superuser
    user.is_staff = is_staff
    user.is_active = True
    return user


class AuditLogViewSetPermissaoTest(SimpleTestCase):
    """Testa que só superuser acessa AuditLogViewSet (não basta is_staff)."""

    def _request_get_logs(self, user):
        """Monta request GET para /audit/logs/ e retorna o status_code."""
        from apps.audit.api.views import AuditLogViewSet
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        raw = factory.get('/audit/logs/')
        force_authenticate(raw, user=user)

        view = AuditLogViewSet.as_view({'get': 'list'})
        # Pula DjangoFilterBackend para não precisar de queryset real de banco.
        empty_qs = MagicMock()
        empty_qs.__iter__ = lambda s: iter([])
        empty_qs.count = lambda: 0
        with patch.object(AuditLogViewSet, 'filter_queryset', return_value=empty_qs), \
             patch.object(AuditLogViewSet, 'get_queryset', return_value=empty_qs):
            resp = view(raw)
        return resp.status_code

    def test_is_staff_sem_superuser_recebe_403(self):
        """Usuário is_staff que não é superuser não pode ver logs cross-tenant."""
        user = _make_user(is_superuser=False, is_staff=True)
        self.assertEqual(self._request_get_logs(user), 403)

    def test_superuser_recebe_200(self):
        """Superuser tem acesso total ao AuditLogViewSet."""
        user = _make_user(is_superuser=True, is_staff=True)
        self.assertEqual(self._request_get_logs(user), 200)

    def test_usuario_anonimo_recebe_403(self):
        """Usuário não autenticado não pode ver logs."""
        from apps.audit.api.views import AuditLogViewSet
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        raw = factory.get('/audit/logs/')

        empty_qs = MagicMock()
        view = AuditLogViewSet.as_view({'get': 'list'})
        with patch.object(AuditLogViewSet, 'filter_queryset', return_value=empty_qs), \
             patch.object(AuditLogViewSet, 'get_queryset', return_value=empty_qs):
            resp = view(raw)
        self.assertIn(resp.status_code, (401, 403))

    def test_my_activity_aceita_usuario_autenticado_comum(self):
        """my_activity é auto-serviço: qualquer usuário autenticado pode acessar.

        O router passa action.kwargs como initkwargs para as_view(), então a
        permission_classes do @action substitui a da classe. Replicamos isso aqui.
        """
        from apps.audit.api.views import AuditLogViewSet
        from rest_framework.test import APIRequestFactory, force_authenticate

        user = _make_user(is_superuser=False, is_staff=False)
        factory = APIRequestFactory()
        raw = factory.get('/audit/logs/my_activity/')
        force_authenticate(raw, user=user)

        # Reproduz o que o router faz: passa os kwargs da @action para as_view.
        action_perms = AuditLogViewSet.my_activity.kwargs.get(
            'permission_classes', AuditLogViewSet.permission_classes
        )
        view = AuditLogViewSet.as_view({'get': 'my_activity'}, permission_classes=action_perms)
        with patch('apps.audit.api.views.AuditService') as mock_svc, \
             patch('apps.audit.api.views.AuditLogSerializer') as mock_ser_cls:
            mock_svc.return_value.get_user_activity.return_value = []
            mock_ser = MagicMock()
            mock_ser.data = []
            mock_ser_cls.return_value = mock_ser
            resp = view(raw)
        self.assertEqual(resp.status_code, 200)


class IsSuperUserPermissaoTest(SimpleTestCase):
    """Testa a classe IsSuperUser isolada."""

    def _perm(self):
        from apps.core.permissions import IsSuperUser
        return IsSuperUser()

    def _view_request(self, user):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.user = user
        return req

    def test_superuser_tem_permissao(self):
        user = _make_user(is_superuser=True)
        self.assertTrue(self._perm().has_permission(self._view_request(user), None))

    def test_staff_sem_superuser_nao_tem_permissao(self):
        user = _make_user(is_superuser=False, is_staff=True)
        self.assertFalse(self._perm().has_permission(self._view_request(user), None))

    def test_usuario_comum_nao_tem_permissao(self):
        user = _make_user(is_superuser=False, is_staff=False)
        self.assertFalse(self._perm().has_permission(self._view_request(user), None))
