"""
Integration tests for combo modal validation scenarios.

Tests that the backend validation rules work correctly for:
1. Required group validation
2. Min/max selections
3. Variant limits
4. Stock availability
5. Duplicate variant handling
"""
import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import (
    Store,
    StoreProduct,
    StoreProductVariant,
    StoreCombo,
)
from apps.stores.models.combo_group import (
    ComboProductGroup,
    ComboProductGroupVariantLimit,
)
from apps.stores.validators import ComboSelectionValidator

User = get_user_model()


class ComboModalValidationTestCase(TestCase):
    """Base test case for combo modal validation tests."""

    def setUp(self):
        """Create test store, products, variants, and combo."""
        self.owner = User.objects.create_user(
            username='modal-validation-owner',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store-modal-validation',
            owner=self.owner,
            status='active'
        )

        # Create test products
        self.product_rondelli = StoreProduct.objects.create(
            store=self.store,
            name='Rondelli',
            slug='rondelli',
            price=29.90,
            track_stock=True,
            stock_quantity=100
        )

        self.product_molho = StoreProduct.objects.create(
            store=self.store,
            name='Molho',
            slug='molho',
            price=5.00,
            track_stock=True,
            stock_quantity=100
        )

        # Create rondelli variants
        self.variant_frango = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Frango',
            stock_quantity=50
        )
        self.variant_carne = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Carne',
            stock_quantity=30
        )
        self.variant_vegetariano = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Vegetariano',
            stock_quantity=20
        )

        # Create molho variants
        self.variant_vinagrete = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Vinagrete',
            stock_quantity=100
        )
        self.variant_maionese = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Maionese',
            stock_quantity=100
        )

        # Create base combo
        self.combo = StoreCombo.objects.create(
            store=self.store,
            name='Modal Test Combo',
            slug='modal-test-combo',
            price=79.90,
            track_stock=False
        )


class ModalRequiredGroupValidationTests(ComboModalValidationTestCase):
    """Tests for required group validation in modal context."""

    def test_required_group_shows_error_when_empty(self):
        """Required group with no selection should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({str(group.id): []})

        self.assertFalse(result)
        self.assertTrue(any('obrigatório' in err for err in validator.errors))

    def test_required_group_passes_with_selection(self):
        """Required group with selection should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({str(group.id): [str(self.variant_frango.id)]})

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_optional_group_passes_when_empty(self):
        """Optional group with no selection should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=False,
            min_selections=0,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({str(group.id): []})

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class ModalMinMaxSelectionValidationTests(ComboModalValidationTestCase):
    """Tests for min/max selection validation in modal context."""

    def test_shows_error_for_below_minimum(self):
        """Selections below minimum should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=4
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=4
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_carne,
            max_selections=4
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [str(self.variant_frango.id)]  # Only 1, needs 2
        })

        self.assertFalse(result)
        self.assertTrue(any('mínimo' in err for err in validator.errors))

    def test_shows_error_for_above_maximum(self):
        """Selections above maximum should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_carne,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_vegetariano,
            max_selections=2
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_carne.id),
                str(self.variant_vegetariano.id)  # 3, exceeds max of 2
            ]
        })

        self.assertFalse(result)
        self.assertTrue(any('máximo' in err for err in validator.errors))

    def test_passes_with_exact_selection_count(self):
        """Exact min/max selection should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_carne,
            max_selections=2
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_carne.id)
            ]
        })

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class ModalVariantLimitValidationTests(ComboModalValidationTestCase):
    """Tests for variant limit validation in modal context."""

    def test_variant_limit_exceeded_shows_error(self):
        """Exceeding per-variant limit should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=4,
            allow_duplicate_variants=True
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2  # Max 2 for this variant
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),
                str(self.variant_frango.id)  # 3 selections exceeds limit
            ]
        })

        self.assertFalse(result)
        self.assertTrue(any('máximo' in err for err in validator.errors))

    def test_variant_limit_respected_passes(self):
        """Respecting per-variant limit should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=4,
            allow_duplicate_variants=True
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_carne,
            max_selections=2
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),  # 2 of frango (at limit)
                str(self.variant_carne.id)    # 1 of carne
            ]
        })

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class ModalStockValidationTests(ComboModalValidationTestCase):
    """Tests for stock availability validation in modal context."""

    def test_zero_stock_variant_fails(self):
        """Zero stock variant selection should fail."""
        # Create zero-stock variant
        variant_no_stock = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Sem Estoque',
            stock_quantity=0
        )

        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=variant_no_stock,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [str(variant_no_stock.id)]
        })

        self.assertFalse(result)
        self.assertTrue(any('estoque' in err for err in validator.errors))

    def test_insufficient_stock_for_quantity_fails(self):
        """Requesting more items than available stock should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=10,
            allow_duplicate_variants=True
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,  # Has 50 stock
            max_selections=10
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [str(self.variant_frango.id)] * 60  # Request 60, available 50
        })

        self.assertFalse(result)
        self.assertTrue(any('estoque' in err for err in validator.errors))

    def test_sufficient_stock_passes(self):
        """Requesting within available stock should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=30,
            allow_duplicate_variants=True
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,  # Has 50 stock
            max_selections=30
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [str(self.variant_frango.id)] * 30  # Request 30, available 50
        })

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class ModalDuplicateValidationTests(ComboModalValidationTestCase):
    """Tests for duplicate variant handling in modal context."""

    def test_duplicates_not_allowed_fails(self):
        """Duplicate selection when not allowed should fail."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=2,
            allow_duplicate_variants=False
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id)  # Same variant twice
            ]
        })

        self.assertFalse(result)
        self.assertTrue(any('duplicada' in err for err in validator.errors))

    def test_duplicates_allowed_passes(self):
        """Duplicate selection when allowed should pass."""
        group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=2,
            allow_duplicate_variants=True
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group,
            variant=self.variant_frango,
            max_selections=2
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id)  # Same variant twice, allowed
            ]
        })

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class ModalComplexScenarioTests(ComboModalValidationTestCase):
    """Tests for complex real-world scenarios."""

    def test_multiple_groups_all_validations(self):
        """Complex: multiple groups with various validation rules."""
        # Rondelli group: 2-4 selections, max 2 per variant
        group1 = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=2,
            max_selections=4,
            allow_duplicate_variants=True,
            position=0
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group1,
            variant=self.variant_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group1,
            variant=self.variant_carne,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group1,
            variant=self.variant_vegetariano,
            max_selections=1
        )

        # Molho group: 1 selection required
        group2 = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_molho,
            is_required=True,
            min_selections=1,
            max_selections=1,
            allow_duplicate_variants=False,
            position=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group2,
            variant=self.variant_vinagrete,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group2,
            variant=self.variant_maionese,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group1.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),  # 2 of frango (at limit)
                str(self.variant_carne.id),   # 1 of carne
                str(self.variant_vegetariano.id)  # 1 of veg (at limit)
            ],
            str(group2.id): [
                str(self.variant_vinagrete.id)
            ]
        })

        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_multiple_groups_with_errors(self):
        """Complex: multiple groups with validation failures."""
        group1 = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group1,
            variant=self.variant_frango,
            max_selections=1
        )

        group2 = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_molho,
            is_required=True,
            min_selections=1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=group2,
            variant=self.variant_vinagrete,
            max_selections=1
        )

        validator = ComboSelectionValidator(self.combo)
        result = validator.validate({
            str(group1.id): [str(self.variant_frango.id)],
            str(group2.id): []  # Missing required selection
        })

        self.assertFalse(result)
        # Should have at least one error (missing molho)
        self.assertGreater(len(validator.errors), 0)
