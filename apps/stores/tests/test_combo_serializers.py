"""
Unit tests for combo serializers.

Test coverage:
- ComboProductGroupVariantLimitSerializer instantiation and serialization
- ComboProductGroupSerializer with nested variant limits
- ComboDetailSerializer with full combo structure (groups + variants)
- ComboListSerializer for summary view
- ComboCreateUpdateSerializer validation
- ComboProductGroupCreateUpdateSerializer validation
- ComboProductGroupVariantLimitCreateUpdateSerializer validation
- Sample data serialization and correctness

Reference: apps/stores/api/combo_serializers.py
"""
import uuid
from decimal import Decimal
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
from apps.stores.api.combo_serializers import (
    ComboProductGroupVariantLimitSerializer,
    ComboProductGroupSerializer,
    ComboDetailSerializer,
    ComboListSerializer,
    ComboCreateUpdateSerializer,
    ComboProductGroupCreateUpdateSerializer,
    ComboProductGroupVariantLimitCreateUpdateSerializer,
)

User = get_user_model()


class ComboSerializerTestCase(TestCase):
    """Base test case with common setup for combo serializer tests."""

    def setUp(self):
        """Create test store, products, variants, and combo."""
        self.owner = User.objects.create_user(
            username='combo-serializer-owner',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store-serializers',
            owner=self.owner,
            status='active'
        )

        # Create two products for combo groups
        self.product_rondelli = StoreProduct.objects.create(
            store=self.store,
            name='Rondelli',
            slug='rondelli',
            price=Decimal('29.90'),
            track_stock=True,
            stock_quantity=100
        )

        self.product_molho = StoreProduct.objects.create(
            store=self.store,
            name='Molho',
            slug='molho',
            price=Decimal('5.00'),
            track_stock=True,
            stock_quantity=100
        )

        # Create variants for rondelli
        self.variant_rondelli_frango = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Frango',
            sku='rondelli-frango',
            stock_quantity=50
        )
        self.variant_rondelli_tomate = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Tomate Seco',
            sku='rondelli-tomate',
            stock_quantity=30
        )
        self.variant_rondelli_queijo = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Queijo',
            sku='rondelli-queijo',
            stock_quantity=40
        )

        # Create variants for molho
        self.variant_molho_branco = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Molho Branco',
            sku='molho-branco',
            stock_quantity=100
        )
        self.variant_molho_vermelho = StoreProductVariant.objects.create(
            product=self.product_molho,
            name='Molho Vermelho',
            sku='molho-vermelho',
            stock_quantity=80
        )

        # Create a combo
        self.combo = StoreCombo.objects.create(
            store=self.store,
            name='Compre 3 Leve 4',
            slug='compre-3-leve-4',
            description='4 Rondelli a preço especial',
            price=Decimal('45.00'),
            compare_at_price=Decimal('59.90'),
            is_active=True,
            featured=False,
        )

        # Create combo groups
        self.group_rondelli = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=4,
            max_selections=4,
            allow_duplicate_variants=True,
            position=1
        )

        self.group_molho = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_molho,
            is_required=False,
            min_selections=0,
            max_selections=4,
            allow_duplicate_variants=True,
            position=2
        )

        # Create variant limits
        self.limit_frango = ComboProductGroupVariantLimit.objects.create(
            group=self.group_rondelli,
            variant=self.variant_rondelli_frango,
            max_selections=2
        )

        self.limit_tomate = ComboProductGroupVariantLimit.objects.create(
            group=self.group_rondelli,
            variant=self.variant_rondelli_tomate,
            max_selections=2
        )

        self.limit_queijo = ComboProductGroupVariantLimit.objects.create(
            group=self.group_rondelli,
            variant=self.variant_rondelli_queijo,
            max_selections=2
        )

        self.limit_molho_branco = ComboProductGroupVariantLimit.objects.create(
            group=self.group_molho,
            variant=self.variant_molho_branco,
            max_selections=2
        )


class ComboProductGroupVariantLimitSerializerTest(ComboSerializerTestCase):
    """Test ComboProductGroupVariantLimitSerializer."""

    def test_serializer_instantiation(self):
        """Test that serializer can be instantiated."""
        serializer = ComboProductGroupVariantLimitSerializer(self.limit_frango)
        self.assertIsNotNone(serializer)

    def test_serializer_fields_present(self):
        """Test that all required fields are present in serialized data."""
        serializer = ComboProductGroupVariantLimitSerializer(self.limit_frango)
        data = serializer.data

        expected_fields = {
            'id', 'variant_id', 'variant_name', 'variant_sku',
            'stock', 'max_selections', 'price_override', 'created_at', 'updated_at'
        }
        self.assertTrue(expected_fields.issubset(set(data.keys())))

    def test_serialize_variant_limit_data(self):
        """Test serialization produces correct data."""
        serializer = ComboProductGroupVariantLimitSerializer(self.limit_frango)
        data = serializer.data

        self.assertEqual(str(data['variant_id']), str(self.variant_rondelli_frango.id))
        self.assertEqual(data['variant_name'], 'Frango')
        self.assertEqual(data['variant_sku'], 'rondelli-frango')
        self.assertEqual(data['stock'], 50)
        self.assertEqual(data['max_selections'], 2)
        self.assertIsNone(data['price_override'])

    def test_serialize_variant_limit_with_price_override(self):
        """Test serialization with price override."""
        # Create a new variant to avoid unique constraint on (group, variant)
        new_variant = StoreProductVariant.objects.create(
            product=self.product_rondelli,
            name='Especial',
            sku='rondelli-especial',
            stock_quantity=25
        )
        limit_with_override = ComboProductGroupVariantLimit.objects.create(
            group=self.group_rondelli,
            variant=new_variant,
            max_selections=3,
            price_override=Decimal('19.90')
        )
        serializer = ComboProductGroupVariantLimitSerializer(limit_with_override)
        data = serializer.data

        self.assertEqual(data['max_selections'], 3)
        self.assertEqual(str(data['price_override']), '19.90')

    def test_serializer_read_only_fields(self):
        """Test that read-only fields cannot be written."""
        data = {
            'variant_id': str(self.variant_rondelli_tomate.id),
            'variant_name': 'Modified Name',
            'max_selections': 5,
            'price_override': None,
        }
        serializer = ComboProductGroupVariantLimitSerializer(
            self.limit_frango,
            data=data,
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        # variant_id and variant_name should remain unchanged (read-only)
        updated = serializer.save()
        self.assertEqual(str(updated.variant.id), str(self.limit_frango.variant.id))
        self.assertEqual(updated.variant.name, 'Frango')


class ComboProductGroupSerializerTest(ComboSerializerTestCase):
    """Test ComboProductGroupSerializer."""

    def test_serializer_instantiation(self):
        """Test that serializer can be instantiated."""
        serializer = ComboProductGroupSerializer(self.group_rondelli)
        self.assertIsNotNone(serializer)

    def test_serializer_fields_present(self):
        """Test that all required fields are present."""
        serializer = ComboProductGroupSerializer(self.group_rondelli)
        data = serializer.data

        expected_fields = {
            'id', 'product_id', 'product_name', 'is_required',
            'min_selections', 'max_selections', 'allow_duplicate_variants',
            'position', 'variant_limits', 'created_at', 'updated_at'
        }
        self.assertTrue(expected_fields.issubset(set(data.keys())))

    def test_serialize_group_data(self):
        """Test serialization produces correct data."""
        serializer = ComboProductGroupSerializer(self.group_rondelli)
        data = serializer.data

        self.assertEqual(str(data['product_id']), str(self.product_rondelli.id))
        self.assertEqual(data['product_name'], 'Rondelli')
        self.assertTrue(data['is_required'])
        self.assertEqual(data['min_selections'], 4)
        self.assertEqual(data['max_selections'], 4)
        self.assertTrue(data['allow_duplicate_variants'])
        self.assertEqual(data['position'], 1)

    def test_serialize_group_with_nested_variants(self):
        """Test serialization includes nested variant limits."""
        serializer = ComboProductGroupSerializer(self.group_rondelli)
        data = serializer.data

        # Should have 3 variants
        self.assertEqual(len(data['variant_limits']), 3)

        # Check variant names
        variant_names = {v['variant_name'] for v in data['variant_limits']}
        self.assertEqual(variant_names, {'Frango', 'Tomate Seco', 'Queijo'})

        # Check first variant limit details
        frango_limit = next(
            (v for v in data['variant_limits'] if v['variant_name'] == 'Frango'),
            None
        )
        self.assertIsNotNone(frango_limit)
        self.assertEqual(frango_limit['max_selections'], 2)
        self.assertEqual(frango_limit['stock'], 50)

    def test_serialize_optional_group(self):
        """Test serialization of optional group."""
        serializer = ComboProductGroupSerializer(self.group_molho)
        data = serializer.data

        self.assertFalse(data['is_required'])
        self.assertEqual(data['min_selections'], 0)
        self.assertEqual(data['max_selections'], 4)


class ComboDetailSerializerTest(ComboSerializerTestCase):
    """Test ComboDetailSerializer."""

    def test_serializer_instantiation(self):
        """Test that serializer can be instantiated."""
        serializer = ComboDetailSerializer(self.combo)
        self.assertIsNotNone(serializer)

    def test_serializer_fields_present(self):
        """Test that all required fields are present."""
        serializer = ComboDetailSerializer(self.combo)
        data = serializer.data

        expected_fields = {
            'id', 'name', 'slug', 'description', 'price', 'compare_at_price',
            'image', 'image_url', 'is_active', 'featured', 'track_stock',
            'stock_quantity', 'sort_order', 'groups', 'created_at', 'updated_at'
        }
        self.assertTrue(expected_fields.issubset(set(data.keys())))

    def test_serialize_combo_data(self):
        """Test serialization produces correct combo data."""
        serializer = ComboDetailSerializer(self.combo)
        data = serializer.data

        self.assertEqual(str(data['id']), str(self.combo.id))
        self.assertEqual(data['name'], 'Compre 3 Leve 4')
        self.assertEqual(data['slug'], 'compre-3-leve-4')
        self.assertEqual(data['description'], '4 Rondelli a preço especial')
        self.assertEqual(data['price'], '45.00')
        self.assertEqual(data['compare_at_price'], '59.90')
        self.assertTrue(data['is_active'])
        self.assertFalse(data['featured'])

    def test_serialize_combo_with_nested_groups(self):
        """Test serialization includes nested groups and variants."""
        serializer = ComboDetailSerializer(self.combo)
        data = serializer.data

        # Should have 2 groups
        self.assertEqual(len(data['groups']), 2)

        # Check group names
        group_products = {g['product_name'] for g in data['groups']}
        self.assertEqual(group_products, {'Rondelli', 'Molho'})

        # Check rondelli group
        rondelli_group = next(
            (g for g in data['groups'] if g['product_name'] == 'Rondelli'),
            None
        )
        self.assertIsNotNone(rondelli_group)
        self.assertTrue(rondelli_group['is_required'])
        self.assertEqual(rondelli_group['min_selections'], 4)
        self.assertEqual(rondelli_group['max_selections'], 4)

        # Check variants in rondelli group
        self.assertEqual(len(rondelli_group['variant_limits']), 3)

        # Check molho group
        molho_group = next(
            (g for g in data['groups'] if g['product_name'] == 'Molho'),
            None
        )
        self.assertIsNotNone(molho_group)
        self.assertFalse(molho_group['is_required'])
        self.assertEqual(molho_group['min_selections'], 0)
        self.assertEqual(molho_group['max_selections'], 4)

    def test_serializer_with_empty_combo(self):
        """Test serialization of combo without groups."""
        empty_combo = StoreCombo.objects.create(
            store=self.store,
            name='Empty Combo',
            slug='empty-combo',
            price=Decimal('10.00'),
            is_active=True,
        )
        serializer = ComboDetailSerializer(empty_combo)
        data = serializer.data

        self.assertEqual(data['name'], 'Empty Combo')
        self.assertEqual(len(data['groups']), 0)


class ComboListSerializerTest(ComboSerializerTestCase):
    """Test ComboListSerializer."""

    def test_serializer_instantiation(self):
        """Test that serializer can be instantiated."""
        serializer = ComboListSerializer(self.combo)
        self.assertIsNotNone(serializer)

    def test_serializer_fields_present(self):
        """Test that all required fields are present."""
        serializer = ComboListSerializer(self.combo)
        data = serializer.data

        expected_fields = {
            'id', 'name', 'slug', 'price', 'compare_at_price',
            'image_url', 'is_active', 'featured', 'groups_count',
            'sort_order', 'created_at', 'updated_at'
        }
        self.assertTrue(expected_fields.issubset(set(data.keys())))

    def test_serialize_combo_list_data(self):
        """Test serialization produces correct summary data."""
        serializer = ComboListSerializer(self.combo)
        data = serializer.data

        self.assertEqual(data['name'], 'Compre 3 Leve 4')
        self.assertEqual(data['price'], '45.00')
        self.assertEqual(data['groups_count'], 2)
        self.assertTrue(data['is_active'])
        self.assertFalse(data['featured'])

    def test_serialize_multiple_combos(self):
        """Test serialization of multiple combos."""
        combo2 = StoreCombo.objects.create(
            store=self.store,
            name='Compre 2 Leve 3',
            slug='compre-2-leve-3',
            price=Decimal('35.00'),
            is_active=True,
        )

        serializer = ComboListSerializer([self.combo, combo2], many=True)
        data = serializer.data

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['name'], 'Compre 3 Leve 4')
        self.assertEqual(data[0]['groups_count'], 2)
        self.assertEqual(data[1]['name'], 'Compre 2 Leve 3')
        self.assertEqual(data[1]['groups_count'], 0)


class ComboCreateUpdateSerializerTest(ComboSerializerTestCase):
    """Test ComboCreateUpdateSerializer."""

    def test_create_combo_valid_data(self):
        """Test creating a combo with valid data."""
        data = {
            'name': 'New Combo',
            'slug': 'new-combo',
            'description': 'A new combo',
            'price': '50.00',
            'compare_at_price': '65.00',
            'is_active': True,
            'featured': False,
            'track_stock': False,
            'stock_quantity': 0,
            'sort_order': 0,
        }
        serializer = ComboCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_create_combo_missing_required_field(self):
        """Test creating combo without required field fails."""
        data = {
            'slug': 'missing-name',
            'price': '50.00',
        }
        serializer = ComboCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('name', serializer.errors)

    def test_validate_price_positive(self):
        """Test that price must be positive."""
        data = {
            'name': 'Invalid Combo',
            'slug': 'invalid-combo',
            'price': '0',
        }
        serializer = ComboCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('price', serializer.errors)

    def test_validate_compare_at_price_greater_than_price(self):
        """Test that compare_at_price must be greater than price."""
        data = {
            'name': 'Invalid Combo',
            'slug': 'invalid-combo',
            'price': '50.00',
            'compare_at_price': '40.00',  # Less than price
        }
        serializer = ComboCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('compare_at_price', serializer.errors)

    def test_validate_compare_at_price_equal_to_price(self):
        """Test that compare_at_price cannot equal price."""
        data = {
            'name': 'Invalid Combo',
            'slug': 'invalid-combo',
            'price': '50.00',
            'compare_at_price': '50.00',  # Equal to price
        }
        serializer = ComboCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('compare_at_price', serializer.errors)

    def test_update_combo_partial(self):
        """Test updating combo with partial data."""
        data = {
            'name': 'Updated Combo Name',
            'price': '55.00',
        }
        serializer = ComboCreateUpdateSerializer(
            self.combo,
            data=data,
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        updated = serializer.save()
        self.assertEqual(updated.name, 'Updated Combo Name')
        self.assertEqual(updated.price, Decimal('55.00'))


class ComboProductGroupCreateUpdateSerializerTest(ComboSerializerTestCase):
    """Test ComboProductGroupCreateUpdateSerializer."""

    def test_create_group_valid_data(self):
        """Test creating a group with valid data."""
        data = {
            'product': self.product_rondelli.id,
            'is_required': True,
            'min_selections': 2,
            'max_selections': 4,
            'allow_duplicate_variants': False,
            'position': 3,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validate_max_selections_positive(self):
        """Test that max_selections must be positive."""
        data = {
            'product': self.product_rondelli.id,
            'max_selections': 0,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_selections', serializer.errors)

    def test_validate_min_selections_less_than_max(self):
        """Test that min_selections must be <= max_selections."""
        data = {
            'product': self.product_rondelli.id,
            'min_selections': 5,
            'max_selections': 3,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('min_selections', serializer.errors)

    def test_validate_required_group_must_have_min_greater_than_zero(self):
        """Test that required groups must have min_selections > 0."""
        data = {
            'product': self.product_rondelli.id,
            'is_required': True,
            'min_selections': 0,  # Invalid for required
            'max_selections': 4,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('min_selections', serializer.errors)

    def test_validate_optional_group_can_have_zero_min(self):
        """Test that optional groups can have min_selections = 0."""
        data = {
            'product': self.product_molho.id,
            'is_required': False,
            'min_selections': 0,
            'max_selections': 4,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_update_group_partial(self):
        """Test updating group with partial data."""
        data = {
            'max_selections': 6,
            'position': 5,
        }
        serializer = ComboProductGroupCreateUpdateSerializer(
            self.group_rondelli,
            data=data,
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        updated = serializer.save()
        self.assertEqual(updated.max_selections, 6)
        self.assertEqual(updated.position, 5)


class ComboProductGroupVariantLimitCreateUpdateSerializerTest(ComboSerializerTestCase):
    """Test ComboProductGroupVariantLimitCreateUpdateSerializer."""

    def test_create_variant_limit_valid_data(self):
        """Test creating variant limit with valid data."""
        data = {
            'variant': self.variant_rondelli_queijo.id,
            'max_selections': 3,
            'price_override': None,
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_create_variant_limit_with_price_override(self):
        """Test creating variant limit with price override."""
        data = {
            'variant': self.variant_rondelli_queijo.id,
            'max_selections': 2,
            'price_override': '25.00',
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validate_max_selections_positive(self):
        """Test that max_selections must be positive."""
        data = {
            'variant': self.variant_rondelli_frango.id,
            'max_selections': 0,
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_selections', serializer.errors)

    def test_validate_price_override_non_negative(self):
        """Test that price_override must be non-negative."""
        data = {
            'variant': self.variant_rondelli_frango.id,
            'max_selections': 2,
            'price_override': '-5.00',
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('price_override', serializer.errors)

    def test_update_variant_limit_partial(self):
        """Test updating variant limit with partial data."""
        data = {
            'max_selections': 5,
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(
            self.limit_frango,
            data=data,
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        updated = serializer.save()
        self.assertEqual(updated.max_selections, 5)
        self.assertEqual(updated.variant.id, self.limit_frango.variant.id)

    def test_update_variant_limit_add_price_override(self):
        """Test adding price override to existing limit."""
        data = {
            'price_override': '22.50',
        }
        serializer = ComboProductGroupVariantLimitCreateUpdateSerializer(
            self.limit_frango,
            data=data,
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        updated = serializer.save()
        self.assertEqual(updated.price_override, Decimal('22.50'))
