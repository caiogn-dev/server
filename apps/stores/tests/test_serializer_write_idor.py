"""Regressão de segurança (IDOR de escrita em serializers): três pontos do
apps/stores/api/serializers.py permitiam que um usuário criasse/editasse
registros em lojas de outros tenants via campo `store` no corpo da request.

Vulnerabilidades cobertas:
  1. StoreSlugOrIdField.to_internal_value — sem verificação de tenant
     Usado em: StoreCouponCreateSerializer.store
     Vetor: POST /api/v1/stores/coupons/ com store=<uuid-de-loja-alheia>

  2. StoreDeliveryZoneCreateSerializer — sem validate_store
     Vetor: POST /api/v1/stores/delivery-zones/ com store=<uuid-de-loja-alheia>

  3. StoreOrderCreateSerializer._resolve_store — usava `not is_staff` em vez de
     `not is_superuser`, is_staff bypassava o check de tenant completamente
     Vetor: POST /api/v1/stores/orders/ com store=<uuid-de-loja-alheia>
     por usuário com is_staff=True

Todos os testes usam SimpleTestCase + mocks (sem banco).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase
from rest_framework import serializers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(is_authenticated=True, is_superuser=False, is_staff=False, user_id=None):
    user = Mock()
    user.is_authenticated = is_authenticated
    user.is_superuser = is_superuser
    user.is_staff = is_staff
    user.id = user_id or uuid.uuid4()
    return user


def _mock_request(user):
    req = Mock()
    req.user = user
    req.query_params = {}
    return req


def _mock_store(store_id=None, owner_id=None):
    store = Mock()
    store.id = store_id or uuid.uuid4()
    store.owner_id = owner_id or uuid.uuid4()
    store.staff = Mock()
    store.staff.filter.return_value.exists.return_value = False
    return store


# ---------------------------------------------------------------------------
# 1. StoreSlugOrIdField — sem verificação de tenant
# ---------------------------------------------------------------------------

class StoreSlugOrIdFieldIDORTest(SimpleTestCase):
    """StoreSlugOrIdField deve bloquear acesso a loja de outro tenant."""

    def _get_field_with_context(self, user):
        from apps.stores.api.serializers import StoreSlugOrIdField
        field = StoreSlugOrIdField()
        field._context = {'request': _mock_request(user)}
        return field

    def test_rejeita_store_nao_acessivel_por_uuid(self):
        """Usuário comum sem acesso à loja deve receber ValidationError."""
        user = _mock_user(is_superuser=False)
        field = self._get_field_with_context(user)
        store_b = _mock_store()
        store_uuid = str(store_b.id)

        with patch('apps.stores.models.Store.objects') as mock_mgr, \
             patch('apps.core.permissions.user_can_access_store', return_value=False):
            mock_mgr.filter.return_value.first.return_value = store_b
            with self.assertRaises(serializers.ValidationError) as ctx:
                field.to_internal_value(store_uuid)
        self.assertIn('não encontrada', str(ctx.exception.detail).lower(),
                      'Mensagem deve ocultar a existência da loja (info-hiding)')

    def test_aceita_store_acessivel(self):
        """Usuário com acesso à loja deve receber o objeto sem erro."""
        user = _mock_user(is_superuser=False)
        field = self._get_field_with_context(user)
        store = _mock_store()
        store_uuid = str(store.id)

        with patch('apps.stores.models.Store.objects') as mock_mgr, \
             patch('apps.core.permissions.user_can_access_store', return_value=True):
            mock_mgr.filter.return_value.first.return_value = store
            result = field.to_internal_value(store_uuid)

        self.assertEqual(result, store)

    def test_superuser_bypassa_check(self):
        """Superuser deve acessar qualquer loja sem verificação."""
        user = _mock_user(is_superuser=True)
        field = self._get_field_with_context(user)
        store_b = _mock_store()
        store_uuid = str(store_b.id)

        with patch('apps.stores.models.Store.objects') as mock_mgr, \
             patch('apps.core.permissions.user_can_access_store') as mock_access:
            mock_mgr.filter.return_value.first.return_value = store_b
            result = field.to_internal_value(store_uuid)

        mock_access.assert_not_called()
        self.assertEqual(result, store_b)

    def test_unauthenticated_sem_contexto_nao_bypassa(self):
        """Sem request no contexto, o check não executa — campo retorna o store
        normalmente; o ViewSet é responsável pela auth. Não deve explodir."""
        field_no_ctx = __import__(
            'apps.stores.api.serializers', fromlist=['StoreSlugOrIdField']
        ).StoreSlugOrIdField()
        field_no_ctx._context = {}
        store = _mock_store()

        with patch('apps.stores.models.Store.objects') as mock_mgr:
            mock_mgr.filter.return_value.first.return_value = store
            result = field_no_ctx.to_internal_value(str(store.id))

        self.assertEqual(result, store)


# ---------------------------------------------------------------------------
# 2. StoreDeliveryZoneCreateSerializer — validate_store ausente
# ---------------------------------------------------------------------------

class DeliveryZoneCreateSerializerIDORTest(SimpleTestCase):
    """StoreDeliveryZoneCreateSerializer.validate_store deve barrar acesso cross-tenant."""

    def _get_serializer_with_context(self, user):
        from apps.stores.api.serializers import StoreDeliveryZoneCreateSerializer
        serializer = StoreDeliveryZoneCreateSerializer()
        serializer._context = {'request': _mock_request(user)}
        return serializer

    def test_validate_store_rejeita_loja_de_outro_tenant(self):
        """validate_store deve lançar ValidationError para loja inacessível."""
        user = _mock_user(is_superuser=False)
        serializer = self._get_serializer_with_context(user)
        store_b = _mock_store()

        with patch('apps.core.permissions.user_can_access_store', return_value=False):
            with self.assertRaises(serializers.ValidationError) as ctx:
                serializer.validate_store(store_b)
        detail = str(ctx.exception.detail).lower()
        self.assertIn('não encontrada', detail)

    def test_validate_store_aceita_loja_acessivel(self):
        """validate_store deve retornar a loja quando o usuário tem acesso."""
        user = _mock_user(is_superuser=False)
        serializer = self._get_serializer_with_context(user)
        store_a = _mock_store()

        with patch('apps.core.permissions.user_can_access_store', return_value=True):
            result = serializer.validate_store(store_a)

        self.assertEqual(result, store_a)

    def test_validate_store_superuser_bypassa(self):
        """Superuser pode usar qualquer loja sem verificação."""
        user = _mock_user(is_superuser=True)
        serializer = self._get_serializer_with_context(user)
        store_b = _mock_store()

        with patch('apps.core.permissions.user_can_access_store') as mock_access:
            result = serializer.validate_store(store_b)

        mock_access.assert_not_called()
        self.assertEqual(result, store_b)

    def test_validate_store_existe_no_serializer(self):
        """StoreDeliveryZoneCreateSerializer deve ter o método validate_store."""
        from apps.stores.api.serializers import StoreDeliveryZoneCreateSerializer
        self.assertTrue(
            hasattr(StoreDeliveryZoneCreateSerializer, 'validate_store'),
            'StoreDeliveryZoneCreateSerializer precisa do método validate_store',
        )


# ---------------------------------------------------------------------------
# 3. StoreOrderCreateSerializer._resolve_store — is_staff bypass
# ---------------------------------------------------------------------------

class OrderCreateResolveStoreIsStaffIDORTest(SimpleTestCase):
    """_resolve_store deve usar is_superuser, não is_staff, para bypass de tenant."""

    def _call_resolve_store(self, user, store):
        """Chama _resolve_store via contexto mockado."""
        from apps.stores.api.serializers import StoreOrderCreateSerializer

        view = Mock()
        view.kwargs = {}
        request = _mock_request(user)
        request.query_params = {}
        request.path = f'/api/v1/stores/orders/'

        serializer = StoreOrderCreateSerializer()
        serializer._context = {'request': request, 'view': view}

        store_uuid = str(store.id)
        validated_data = {'store': store_uuid}

        with patch('apps.stores.models.Store.objects') as mock_mgr:
            mock_mgr.filter.return_value.first.return_value = store
            try:
                uuid.UUID(store_uuid)
                mock_mgr.filter.return_value.first.return_value = store
            except ValueError:
                pass
            return serializer._resolve_store(validated_data)

    def test_is_staff_sem_acesso_nao_bypassa_tenant_check(self):
        """is_staff SEM ser owner/staff da loja deve ser bloqueado (ValidationError)."""
        attacker_id = uuid.uuid4()
        user = _mock_user(is_staff=True, is_superuser=False, user_id=attacker_id)
        other_owner_id = uuid.uuid4()
        store = _mock_store(owner_id=other_owner_id)
        # is_staff do attacker não está no M2M store.staff
        store.staff.filter.return_value.exists.return_value = False

        with self.assertRaises(serializers.ValidationError) as ctx:
            self._call_resolve_store(user, store)

        detail = str(ctx.exception.detail).lower()
        self.assertIn('access', detail, 'Deve reportar falta de acesso')

    def test_is_staff_que_e_owner_tem_acesso(self):
        """is_staff que também é owner da loja deve ter acesso normalmente."""
        user_id = uuid.uuid4()
        user = _mock_user(is_staff=True, is_superuser=False, user_id=user_id)
        store = _mock_store(owner_id=user_id)

        result = self._call_resolve_store(user, store)
        self.assertEqual(result, store)

    def test_is_superuser_bypassa_check(self):
        """is_superuser (não is_staff) é o único que pode bypassar o check de tenant."""
        user_id = uuid.uuid4()
        user = _mock_user(is_staff=False, is_superuser=True, user_id=user_id)
        other_owner_id = uuid.uuid4()
        store = _mock_store(owner_id=other_owner_id)
        store.staff.filter.return_value.exists.return_value = False

        # Não deve levantar
        result = self._call_resolve_store(user, store)
        self.assertEqual(result, store)

    def test_is_staff_check_usa_is_superuser_nao_is_staff(self):
        """_resolve_store não pode ter `not user.is_staff` no guard de tenant."""
        import inspect
        from apps.stores.api.serializers import StoreOrderCreateSerializer
        src = inspect.getsource(StoreOrderCreateSerializer._resolve_store)
        self.assertNotIn('not request.user.is_staff', src,
                         '_resolve_store usa is_staff para bypass — deve usar is_superuser')
        self.assertNotIn('not user.is_staff', src,
                         '_resolve_store usa is_staff para bypass — deve usar is_superuser')
