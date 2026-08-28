"""
Testes de regressão para IDOR de escrita em StoreCategorySerializer e
StoreProductCreateSerializer — campos `store`, `parent` e `category` sem gate
de tenant permitem mover categorias e produtos para lojas alheias via PATCH/PUT.

RED → GREEN confirmado: executar ANTES e DEPOIS do fix.
Todos são SimpleTestCase (sem DB, sem Docker).
"""
import types
import uuid
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase


def _make_request(user):
    req = MagicMock()
    req.user = user
    return req


def _make_user(is_superuser=False, is_authenticated=True):
    user = MagicMock()
    user.is_superuser = is_superuser
    user.is_authenticated = is_authenticated
    return user


def _make_store(store_id=None):
    store = MagicMock()
    store.id = store_id or uuid.uuid4()
    return store


class TestStoreCategorySerializerValidateStore(SimpleTestCase):
    """validate_store bloqueia atribuição de categoria a loja alheia."""

    def _get_serializer(self, user, can_access=True):
        from apps.stores.api.serializers import StoreCategorySerializer
        request = _make_request(user)
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=can_access) as _mock:
            ser = StoreCategorySerializer(context={'request': request})
            ser._mock_ucan = _mock
        return ser, _mock

    def test_superuser_bypassa_gate(self):
        """Superuser pode atribuir categoria a qualquer loja."""
        from apps.stores.api.serializers import StoreCategorySerializer
        user = _make_user(is_superuser=True)
        request = _make_request(user)
        ser = StoreCategorySerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store') as mock_ucan:
            result = ser.validate_store(store)
        self.assertEqual(result, store)
        mock_ucan.assert_not_called()

    def test_usuario_com_acesso_passa(self):
        """Usuário com acesso à loja pode atribuir normalmente."""
        from apps.stores.api.serializers import StoreCategorySerializer
        from rest_framework import serializers as drf_serializers
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreCategorySerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=True):
            result = ser.validate_store(store)
        self.assertEqual(result, store)

    def test_usuario_sem_acesso_levanta_validation_error(self):
        """Usuário sem acesso à loja alvo recebe ValidationError (info-hiding)."""
        from apps.stores.api.serializers import StoreCategorySerializer
        from rest_framework import serializers as drf_serializers
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreCategorySerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                ser.validate_store(store)

    def test_mensagem_info_hiding(self):
        """ValidationError usa mensagem genérica ('Loja não encontrada'), não 403."""
        from apps.stores.api.serializers import StoreCategorySerializer
        from rest_framework import serializers as drf_serializers
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreCategorySerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=False):
            try:
                ser.validate_store(store)
                self.fail("Deveria ter levantado ValidationError")
            except drf_serializers.ValidationError as exc:
                detail = exc.detail
                msg = detail[0] if isinstance(detail, list) else str(detail)
                self.assertIn('não encontrada', str(msg).lower())


class TestStoreProductCreateSerializerValidateStore(SimpleTestCase):
    """validate_store em StoreProductCreateSerializer bloqueia produto cross-tenant."""

    def test_superuser_bypassa_gate(self):
        """Superuser pode criar produto em qualquer loja."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        user = _make_user(is_superuser=True)
        request = _make_request(user)
        ser = StoreProductCreateSerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store') as mock_ucan:
            result = ser.validate_store(store)
        self.assertEqual(result, store)
        mock_ucan.assert_not_called()

    def test_usuario_com_acesso_passa(self):
        """Usuário com acesso à loja pode criar produto normalmente."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreProductCreateSerializer(context={'request': request})
        store = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=True):
            result = ser.validate_store(store)
        self.assertEqual(result, store)

    def test_usuario_sem_acesso_loja_alheia_levanta_error(self):
        """POST com store de outra loja → ValidationError (IDOR bloqueado)."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        from rest_framework import serializers as drf_serializers
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreProductCreateSerializer(context={'request': request})
        store_alheio = _make_store()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                ser.validate_store(store_alheio)

    def test_validate_category_bloqueia_categoria_alheia(self):
        """validate_category bloqueia categoria de loja alheia."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        from rest_framework import serializers as drf_serializers
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreProductCreateSerializer(context={'request': request})
        category = MagicMock()
        category.store_id = uuid.uuid4()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=False):
            with self.assertRaises(drf_serializers.ValidationError):
                ser.validate_category(category)

    def test_validate_category_passa_para_categoria_propria(self):
        """validate_category permite categoria da própria loja."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        user = _make_user(is_superuser=False)
        request = _make_request(user)
        ser = StoreProductCreateSerializer(context={'request': request})
        category = MagicMock()
        category.store_id = uuid.uuid4()
        with patch('apps.stores.api.serializers.user_can_access_store', return_value=True):
            result = ser.validate_category(category)
        self.assertEqual(result, category)


class TestStaticAnalysis(SimpleTestCase):
    """Verificações estáticas garantem que o fix foi aplicado nos dois serializers."""

    def test_category_serializer_tem_validate_store(self):
        """StoreCategorySerializer deve ter método validate_store."""
        from apps.stores.api.serializers import StoreCategorySerializer
        self.assertTrue(
            hasattr(StoreCategorySerializer, 'validate_store'),
            "StoreCategorySerializer não tem validate_store — IDOR não corrigido"
        )

    def test_product_create_serializer_tem_validate_store(self):
        """StoreProductCreateSerializer deve ter método validate_store."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        self.assertTrue(
            hasattr(StoreProductCreateSerializer, 'validate_store'),
            "StoreProductCreateSerializer não tem validate_store — IDOR não corrigido"
        )

    def test_product_create_serializer_tem_validate_category(self):
        """StoreProductCreateSerializer deve ter método validate_category."""
        from apps.stores.api.serializers import StoreProductCreateSerializer
        self.assertTrue(
            hasattr(StoreProductCreateSerializer, 'validate_category'),
            "StoreProductCreateSerializer não tem validate_category — IDOR de categoria não corrigido"
        )

    def test_category_serializer_tem_validate_parent(self):
        """StoreCategorySerializer deve ter validate_parent para bloquear pai cross-tenant."""
        from apps.stores.api.serializers import StoreCategorySerializer
        self.assertTrue(
            hasattr(StoreCategorySerializer, 'validate_parent'),
            "StoreCategorySerializer não tem validate_parent — cross-tenant parent não corrigido"
        )
