"""Testes TDD para AuditLogViewSet — garante que is_staff sem is_superuser
é recusado (convenção multi-tenant: acesso cross-tenant exige is_superuser).

Referência: apps/core/permissions.py linhas 276-297 e CLAUDE.md
("is_superuser (NOT is_staff) for cross-tenant owner").
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


class AuditLogViewSetPermissaoTest(TestCase):
    """AuditLogViewSet exige is_superuser; is_staff apenas NÃO é suficiente."""

    def setUp(self):
        self.client = APIClient()

    def _url(self, suffix=''):
        return f'/api/v1/audit/logs/{suffix}'

    def test_anonimo_e_recusado(self):
        response = self.client.get(self._url())
        self.assertIn(response.status_code, (401, 403))

    def test_is_staff_sem_superuser_e_recusado_na_lista(self):
        """is_staff sem is_superuser NÃO pode acessar lista de audit logs."""
        user = User.objects.create_user(
            username='staff_only', password='x', is_staff=True, is_superuser=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403,
                         "is_staff sem is_superuser deve ser recusado (403)")

    def test_is_staff_sem_superuser_e_recusado_no_object_history(self):
        """is_staff sem is_superuser NÃO pode consultar object_history."""
        user = User.objects.create_user(
            username='staff_hist', password='x', is_staff=True, is_superuser=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self._url('object_history/?type=storeorder&id=1'))
        self.assertEqual(response.status_code, 403,
                         "object_history deve exigir is_superuser")

    def test_superuser_pode_listar_logs(self):
        """Superuser tem acesso aos audit logs."""
        user = User.objects.create_user(
            username='superusr', password='x', is_superuser=True, is_staff=True
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_my_activity_nao_exige_superuser(self):
        """my_activity exige apenas autenticação — mostra atividade do próprio usuário."""
        user = User.objects.create_user(
            username='user_comum', password='x', is_staff=False, is_superuser=False
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self._url('my_activity/'))
        self.assertEqual(response.status_code, 200,
                         "my_activity deve ser acessível a qualquer usuário autenticado")
