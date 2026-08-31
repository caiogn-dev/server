"""
Regressão de segurança: UnifiedUserViewSet.get_or_create — IDOR / divulgação de PII [P1]

POST /api/v1/users/users/get_or_create/
  - Qualquer usuário IsAuthenticated conseguia sondar perfis de clientes de
    outros tenants fornecendo o telefone.
  - A resposta inclui: email, google_id, total_spent, abandoned_cart_items,
    context_for_agent — PII grave cruzando fronteiras de tenant.

Convenção do projeto: is_staff (acesso ao /admin) NÃO concede acesso
cross-tenant. get_or_create é operação interna de bot/automação → exige
is_superuser.
"""
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.users.views import UnifiedUserViewSet


def _make_user(is_superuser=False, is_staff=False):
    u = MagicMock()
    u.is_authenticated = True
    u.is_superuser = is_superuser
    u.is_staff = is_staff
    return u


def _make_request(user, data=None):
    factory = APIRequestFactory()
    request = factory.post('/api/v1/users/users/get_or_create/', data or {}, format='json')
    request.user = user
    # DRF precisa de request autenticado sem sessão real
    request._force_auth_user = user
    return request


class GetOrCreateSuperuserGateTest(SimpleTestCase):
    """Usuário regular não pode chamar get_or_create — gate superuser."""

    def test_unauthenticated_sem_gate_antes_do_fix(self):
        """A action existe no viewset com método POST."""
        actions = {m: a for m, a in UnifiedUserViewSet.__dict__.items()
                   if callable(getattr(UnifiedUserViewSet, m, None)) and
                   getattr(getattr(UnifiedUserViewSet, m, None), 'url_path', None) == 'get_or_create'}
        # A action deve existir no viewset
        self.assertIn('get_or_create', dir(UnifiedUserViewSet))

    def test_usuario_regular_recebe_403(self):
        """Usuário autenticado mas não-superuser → 403."""
        view = UnifiedUserViewSet.as_view({'post': 'get_or_create'})
        request = _make_request(_make_user(is_superuser=False), {'phone_number': '+5511999999999'})
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_is_staff_recebe_403(self):
        """is_staff (acesso ao /admin) NÃO concede acesso — deve retornar 403."""
        view = UnifiedUserViewSet.as_view({'post': 'get_or_create'})
        request = _make_request(_make_user(is_superuser=False, is_staff=True),
                                {'phone_number': '+5511888888888'})
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_sem_telefone_retorna_400_para_superuser(self):
        """Superuser sem phone_number → 400 (não 403 nem 500)."""
        view = UnifiedUserViewSet.as_view({'post': 'get_or_create'})
        request = _make_request(_make_user(is_superuser=True), {})
        with patch('apps.users.views.UnifiedUser.objects.get_or_create') as mock_goc:
            response = view(request)
        # Superuser chega ao check de phone antes de qualquer DB call
        self.assertEqual(response.status_code, 400)

    def test_superuser_pode_chamar(self):
        """Superuser → prossegue para lookup/criação (sem gate 403)."""
        fake_user = MagicMock()
        fake_user.pk = 42
        view = UnifiedUserViewSet.as_view({'post': 'get_or_create'})
        request = _make_request(_make_user(is_superuser=True), {'phone_number': '+5511777777777'})
        with patch('apps.users.views.UnifiedUser.objects.get_or_create',
                   return_value=(fake_user, True)) as mock_goc, \
             patch.object(UnifiedUserViewSet, 'get_serializer') as mock_ser:
            mock_ser.return_value.data = {'id': '42', 'phone_number': '+5511777777777'}
            response = view(request)
        # Superuser não recebe 403
        self.assertNotEqual(response.status_code, 403)

    def test_usuario_regular_nao_recebe_dados_de_outro_tenant(self):
        """Gate deve bloquear ANTES do DB — get_or_create jamais deve ser chamado."""
        view = UnifiedUserViewSet.as_view({'post': 'get_or_create'})
        request = _make_request(_make_user(is_superuser=False),
                                {'phone_number': '+5521999999999'})
        fake_uu = MagicMock()
        # Se o gate não existe, get_or_create é chamado (mock previne erro de DB).
        # Após o fix, o gate retorna 403 antes de chegar aqui.
        with patch('apps.users.views.UnifiedUser.objects.get_or_create',
                   return_value=(fake_uu, False)) as mock_goc, \
             patch.object(UnifiedUserViewSet, 'get_serializer',
                          return_value=MagicMock(data={})):
            response = view(request)
        # Após o fix: gate retorna 403 e get_or_create nunca foi chamado.
        mock_goc.assert_not_called()
        self.assertEqual(response.status_code, 403)
