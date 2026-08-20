"""
ProductNutritionProfileSerializer.validate_product deve recusar produtos de
outros tenants, impedindo IDOR de escrita cross-tenant no perfil nutricional.

O impacto é crítico porque o perfil alimenta a view pública AllowAny
/api/v1/nutrition/public/<product_id>/ (QR Code ANVISA) — dados adulterados
seriam exibidos como rótulo nutricional oficial de produtos alheios.

Testes rodados sem DB (SimpleTestCase + mocks) — sem dependências externas.
"""
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.nutrition.api.serializers import ProductNutritionProfileSerializer


def _user(is_superuser=False, uid=1):
    u = MagicMock()
    u.id = uid
    u.is_superuser = is_superuser
    return u


def _product(owner_id, is_staff_of=False):
    """
    Retorna um produto mock com store.owner_id = owner_id.
    is_staff_of=True simula que user.id=1 está no staff da loja.
    """
    staff_qs = MagicMock()
    staff_qs.exists.return_value = is_staff_of
    store = MagicMock()
    store.owner_id = owner_id
    store.staff.filter.return_value = staff_qs
    product = MagicMock()
    product.store = store
    return product


def _serializer(user):
    request = MagicMock()
    request.user = user
    return ProductNutritionProfileSerializer(context={"request": request})


class TestProductNutritionProfileIDOR(SimpleTestCase):
    """
    Garante que validate_product existe e aplica isolamento de tenant.
    Replicação do padrão de ProductRecipeSerializer.validate_product.
    """

    # --- análise estática ---------------------------------------------------

    def test_validate_product_existe_no_serializer(self):
        """Serializer deve declarar validate_product — garante que a correção persiste."""
        self.assertTrue(
            hasattr(ProductNutritionProfileSerializer, "validate_product"),
            "ProductNutritionProfileSerializer.validate_product ausente — IDOR write aberto",
        )

    def test_validate_product_e_callable(self):
        self.assertTrue(callable(ProductNutritionProfileSerializer.validate_product))

    # --- dono da loja -------------------------------------------------------

    def test_dono_pode_criar_perfil_do_proprio_produto(self):
        user = _user(uid=42)
        product = _product(owner_id=42)
        s = _serializer(user)
        result = s.validate_product(product)
        self.assertIs(result, product)

    # --- staff da loja ------------------------------------------------------

    def test_staff_da_loja_pode_criar_perfil(self):
        user = _user(uid=1)
        product = _product(owner_id=999, is_staff_of=True)
        s = _serializer(user)
        result = s.validate_product(product)
        self.assertIs(result, product)

    # --- superuser ----------------------------------------------------------

    def test_superuser_pode_criar_perfil_de_qualquer_loja(self):
        user = _user(is_superuser=True, uid=1)
        product = _product(owner_id=999)  # loja de outro tenant
        s = _serializer(user)
        result = s.validate_product(product)
        self.assertIs(result, product)

    def test_superuser_nao_chama_staff_filter(self):
        """Superuser bypassa sem acessar o banco (staff.filter não deve ser chamado)."""
        user = _user(is_superuser=True)
        product = _product(owner_id=999)
        s = _serializer(user)
        s.validate_product(product)
        product.store.staff.filter.assert_not_called()

    # --- atacante (IDOR bloqueado) ------------------------------------------

    def test_atacante_nao_pode_criar_perfil_de_produto_alheio(self):
        """POST /nutrition/profiles/ com product=<id_alheio> deve levantar ValidationError."""
        user = _user(uid=1)
        product = _product(owner_id=999, is_staff_of=False)
        s = _serializer(user)
        with self.assertRaises(DRFValidationError):
            s.validate_product(product)

    def test_mensagem_de_erro_nao_revela_existencia_do_produto(self):
        """Info-hiding: mensagem genérica — mesmo comportamento de ProductRecipeSerializer."""
        user = _user(uid=1)
        product = _product(owner_id=999, is_staff_of=False)
        s = _serializer(user)
        with self.assertRaises(DRFValidationError) as ctx:
            s.validate_product(product)
        msg = str(ctx.exception).lower()
        self.assertIn("autorizado", msg)

    def test_nao_staff_e_nao_owner_bloqueado(self):
        """Usuário autenticado mas sem relação com a loja deve ser bloqueado."""
        user = _user(uid=7)
        product = _product(owner_id=42, is_staff_of=False)
        s = _serializer(user)
        with self.assertRaises(DRFValidationError):
            s.validate_product(product)
