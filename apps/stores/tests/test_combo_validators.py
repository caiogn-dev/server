"""
Unit tests for ComboSelectionValidator.

Test coverage:
- Required groups validation
- Min/max selection counts
- Duplicate variant handling
- Per-variant limits
- Stock availability checks
- Edge cases (unknown groups, invalid variants, etc.)
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


class ComboSelectionValidatorTestCase(TestCase):
    """Base test case with common setup for combo validator tests."""

    def setUp(self):
        """Create test store, products, variants, and combo."""
        self.owner = User.objects.create_user(
            username='combo-test-owner',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store-combo',
            owner=self.owner,
            status='active'
        )

        # Create two products for combo groups
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

        # Create variants for rondelli
        self.variant_rondelli_frango = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Frango',
            stock_quantity=50
        )
        self.variant_rondelli_carne = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Carne',
            stock_quantity=30
        )
        self.variant_rondelli_vegetariano = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Vegetariano',
            stock_quantity=20
        )
        self.variant_rondelli_camarao = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Camarão',
            stock_quantity=15
        )

        # Create variants for molho
        self.variant_molho_vinagrete = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Vinagrete',
            stock_quantity=100
        )
        self.variant_molho_maionese = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Maionese',
            stock_quantity=100
        )
        self.variant_molho_mostarda = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Mostarda',
            stock_quantity=100
        )

        # Create combo
        self.combo = StoreCombo.objects.create(
            store=self.store,
            name='Combo Premium',
            slug='combo-premium',
            price=79.90,
            track_stock=False
        )

    def _create_combo_with_groups(
        self,
        groups_config: list
    ) -> StoreCombo:
        """
        Helper to create a combo with specified groups.

        Args:
            groups_config: List of dicts with keys:
                - product: StoreProduct instance
                - is_required: bool (default True)
                - min_selections: int (default 1)
                - max_selections: int (default 1)
                - allow_duplicate_variants: bool (default False)
                - variant_limits: dict mapping variant → max_selections (optional)

        Returns:
            StoreCombo instance with groups and limits configured
        """
        combo = StoreCombo.objects.create(
            store=self.store,
            name='Custom Combo',
            slug=f'custom-combo-{uuid.uuid4().hex[:8]}',
            price=99.90,
            track_stock=False
        )

        for i, config in enumerate(groups_config):
            group = ComboProductGroup.objects.create(
                combo=combo,
                product=config['product'],
                is_required=config.get('is_required', True),
                min_selections=config.get('min_selections', 1),
                max_selections=config.get('max_selections', 1),
                allow_duplicate_variants=config.get('allow_duplicate_variants', False),
                position=i
            )

            # Create variant limits if specified
            if 'variant_limits' in config:
                for variant, max_sel in config['variant_limits'].items():
                    ComboProductGroupVariantLimit.objects.create(
                        group=group,
                        variant=variant,
                        max_selections=max_sel
                    )

        return combo


class RequiredGroupsValidationTests(ComboSelectionValidatorTestCase):
    """Tests for required group validation."""

    def test_required_group_with_selection_passes(self):
        """Required group with selection should pass validation."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [str(self.variant_rondelli_frango.id)]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_required_group_without_selection_fails(self):
        """Required group without selection should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: []
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('obrigatório' in err for err in validator.errors))

    def test_required_group_missing_from_selections_fails(self):
        """Required group completely missing from selections should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True
            }
        ])

        validator = ComboSelectionValidator(combo)
        selections = {}  # Empty selections

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('obrigatório' in err for err in validator.errors))

    def test_optional_group_without_selection_passes(self):
        """Optional group without selection should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': False,
                'min_selections': 0,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: []
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_multiple_required_groups_all_selected_passes(self):
        """Multiple required groups, all with selections, should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1
            },
            {
                'product': self.product_molho,
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        groups = list(combo.groups.all())
        group_rondelli_id = str(groups[0].id)
        group_molho_id = str(groups[1].id)

        validator = ComboSelectionValidator(combo)
        selections = {
            group_rondelli_id: [str(self.variant_rondelli_frango.id)],
            group_molho_id: [str(self.variant_molho_vinagrete.id)]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_multiple_required_groups_one_missing_fails(self):
        """Multiple required groups, one missing, should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True
            },
            {
                'product': self.product_molho,
                'is_required': True
            }
        ])

        groups = list(combo.groups.all())
        group_rondelli_id = str(groups[0].id)

        validator = ComboSelectionValidator(combo)
        selections = {
            group_rondelli_id: [str(self.variant_rondelli_frango.id)]
            # molho group missing
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('obrigatório' in err for err in validator.errors))


class MinMaxSelectionTests(ComboSelectionValidatorTestCase):
    """Tests for min/max selection count validation."""

    def test_min_selections_met_passes(self):
        """Meeting minimum selections should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 4
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id)
            ]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_min_selections_not_met_fails(self):
        """Not meeting minimum selections should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 3,
                'max_selections': 4
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id)
            ]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('mínimo' in err for err in validator.errors))

    def test_max_selections_respected_passes(self):
        """Not exceeding maximum selections should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 2
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id)
            ]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_max_selections_exceeded_fails(self):
        """Exceeding maximum selections should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 2
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id),
                str(self.variant_rondelli_vegetariano.id)
            ]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('máximo' in err for err in validator.errors))

    def test_exact_max_selections_passes(self):
        """Selecting exactly max allowed should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 4,
                'max_selections': 4
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id),
                str(self.variant_rondelli_vegetariano.id),
                str(self.variant_rondelli_camarao.id)
            ]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class DuplicateVariantTests(ComboSelectionValidatorTestCase):
    """Tests for duplicate variant handling."""

    def test_duplicates_not_allowed_with_duplicates_fails(self):
        """Duplicates in selection when not allowed should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 2,
                'allow_duplicate_variants': False
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        variant_id = str(self.variant_rondelli_frango.id)
        selections = {
            group_id: [variant_id, variant_id]  # Same variant twice
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('duplicada' in err for err in validator.errors))

    def test_duplicates_allowed_with_duplicates_passes(self):
        """Duplicates in selection when allowed should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 4,
                'allow_duplicate_variants': True
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        variant_id = str(self.variant_rondelli_frango.id)
        selections = {
            group_id: [variant_id, variant_id]  # Same variant twice, but allowed
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_no_duplicates_with_different_variants_passes(self):
        """Different variants should always pass duplicate check."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 2,
                'allow_duplicate_variants': False
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id)
            ]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class VariantLimitTests(ComboSelectionValidatorTestCase):
    """Tests for per-variant selection limits."""

    def test_variant_limit_respected_passes(self):
        """Respecting per-variant limit should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 4,
                'allow_duplicate_variants': True,
                'variant_limits': {
                    self.variant_rondelli_frango: 2,
                    self.variant_rondelli_carne: 2
                }
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        variant_frango = str(self.variant_rondelli_frango.id)
        variant_carne = str(self.variant_rondelli_carne.id)
        selections = {
            group_id: [
                variant_frango,
                variant_frango,  # 2 frango (at limit)
                variant_carne,
            ]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_variant_limit_exceeded_fails(self):
        """Exceeding per-variant limit should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 4,
                'allow_duplicate_variants': True,
                'variant_limits': {
                    self.variant_rondelli_frango: 2,
                }
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        variant_frango = str(self.variant_rondelli_frango.id)
        selections = {
            group_id: [
                variant_frango,
                variant_frango,
                variant_frango,  # 3 frango (exceeds limit of 2)
            ]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('máximo' in err for err in validator.errors))

    def test_unknown_variant_fails(self):
        """Unknown variant ID should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        unknown_id = str(uuid.uuid4())
        selections = {
            group_id: [unknown_id]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('desconhecida' in err for err in validator.errors))

    def test_variant_from_wrong_product_fails(self):
        """Variant not belonging to group's product should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        # Try to use molho variant in rondelli group
        selections = {
            group_id: [str(self.variant_molho_vinagrete.id)]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('não pertence' in err for err in validator.errors))


class StockAvailabilityTests(ComboSelectionValidatorTestCase):
    """Tests for stock availability validation."""

    def test_stock_available_passes(self):
        """Sufficient stock should pass."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 2,
                'max_selections': 30,
                'allow_duplicate_variants': True
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        # variant_rondelli_frango has 50 stock
        variant_id = str(self.variant_rondelli_frango.id)
        selections = {
            group_id: [variant_id] * 30  # Request 30, available 50
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)

    def test_stock_insufficient_fails(self):
        """Insufficient stock should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'min_selections': 1,
                'max_selections': 100,
                'allow_duplicate_variants': True
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        # variant_rondelli_camarao has 15 stock
        variant_id = str(self.variant_rondelli_camarao.id)
        selections = {
            group_id: [variant_id] * 20  # Request 20, available 15
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('estoque' in err for err in validator.errors))

    def test_stock_not_tracked_passes_with_zero_stock(self):
        """Variant with zero stock but product doesn't track stock should pass."""
        # Create product that doesn't track stock
        product_no_track = StoreProduct.objects.create(
            store=self.store,
            name='Product No Track',
            slug='product-no-track',
            price=10.00,
            track_stock=False,  # Don't track
            stock_quantity=0
        )

        variant_no_track = StoreProductVariant.objects.create(
            product=product_no_track,
            name='Variant No Track',
            stock_quantity=0
        )

        combo = self._create_combo_with_groups([
            {
                'product': product_no_track,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [str(variant_no_track.id)]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)


class EdgeCaseTests(ComboSelectionValidatorTestCase):
    """Tests for edge cases and error conditions."""

    def test_unknown_group_id_fails(self):
        """Selection for unknown group should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True
            }
        ])

        validator = ComboSelectionValidator(combo)
        unknown_group_id = str(uuid.uuid4())
        selections = {
            unknown_group_id: [str(self.variant_rondelli_frango.id)]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        self.assertTrue(any('desconhecido' in err for err in validator.errors))

    def test_empty_selections_dict_fails_with_required_groups(self):
        """Empty selections dict with required groups should fail."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True
            }
        ])

        validator = ComboSelectionValidator(combo)
        selections = {}

        result = validator.validate(selections)
        self.assertFalse(result)

    def test_multiple_errors_collected(self):
        """Multiple validation errors should be collected."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True,
                'min_selections': 3,
                'max_selections': 3
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)
        selections = {
            group_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_molho_vinagrete.id),  # Wrong product
            ]
        }

        result = validator.validate(selections)
        self.assertFalse(result)
        # Should have at least 2 errors: wrong product + min selections not met
        self.assertGreaterEqual(len(validator.errors), 2)

    def test_validate_resets_errors(self):
        """Calling validate again should reset errors list."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True
            }
        ])

        group_id = str(combo.groups.first().id)
        validator = ComboSelectionValidator(combo)

        # First validation fails
        selections_fail = {group_id: []}
        result1 = validator.validate(selections_fail)
        self.assertFalse(result1)
        self.assertGreater(len(validator.errors), 0)

        # Second validation passes
        selections_pass = {group_id: [str(self.variant_rondelli_frango.id)]}
        result2 = validator.validate(selections_pass)
        self.assertTrue(result2)
        self.assertEqual(len(validator.errors), 0)

    def test_complex_scenario_multiple_groups_and_variants(self):
        """Complex scenario: multiple groups, limits, duplicates, and stock."""
        combo = self._create_combo_with_groups([
            {
                'product': self.product_rondelli,
                'is_required': True,
                'min_selections': 2,
                'max_selections': 4,
                'allow_duplicate_variants': True,
                'variant_limits': {
                    self.variant_rondelli_frango: 2,
                    self.variant_rondelli_carne: 2,
                    self.variant_rondelli_vegetariano: 1,
                }
            },
            {
                'product': self.product_molho,
                'is_required': True,
                'min_selections': 1,
                'max_selections': 1
            }
        ])

        groups = list(combo.groups.all())
        group_rondelli_id = str(groups[0].id)
        group_molho_id = str(groups[1].id)

        validator = ComboSelectionValidator(combo)
        selections = {
            group_rondelli_id: [
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_frango.id),
                str(self.variant_rondelli_carne.id),
                str(self.variant_rondelli_vegetariano.id)
            ],
            group_molho_id: [str(self.variant_molho_maionese.id)]
        }

        result = validator.validate(selections)
        self.assertTrue(result)
        self.assertEqual(len(validator.errors), 0)
