"""
Integration tests for Combo API endpoints.

Test coverage:
- Combo detail (dashboard): GET /api/v1/stores/combos/{combo_id}/
- Combo list (dashboard):   GET /api/v1/stores/combos/?store=<slug>&is_active=true
- AddComboToCartView:       POST /api/v1/stores/{store_slug}/cart/add-combo/

Note: the combo CRUD routes the dashboard consumes are the global DRF router
routes (/api/v1/stores/combos/, see apps/stores/urls.py ~line 132). The
storefront catch-all <slug:store_slug>/ does NOT expose a nested combos route;
public storefront combos are served by apps.public_api at
/api/v1/public/<slug>/combos/.

Tests:
- List combos with pagination and filtering
- Get combo detail with groups, variants, stock info
- Add combo to cart with valid selections
- Tenant isolation (combo from other store returns 404)
- Selection validation (required groups, min/max selections, duplicates, stock)
"""
import uuid as uuid_module
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from apps.stores.models import (
    Store,
    StoreProduct,
    StoreProductVariant,
    StoreCombo,
    StoreCart,
    StoreCartComboItem,
)
from apps.stores.models.combo_group import (
    ComboProductGroup,
    ComboProductGroupVariantLimit,
)

User = get_user_model()


class ComboDetailViewTestCase(APITestCase):
    """Tests for GET /api/v1/stores/combos/{combo_id}/ (admin/dashboard route).

    The combo CRUD endpoints the dashboard actually consumes are the global
    DRF router routes mounted at /api/v1/stores/combos/ (see
    apps/stores/urls.py line ~132 and pastita-dash storesApi.getCombo). The
    storefront catch-all <slug:store_slug>/ does NOT expose a combos route;
    public combo listing lives under /api/v1/public/<slug>/combos/.
    """

    def setUp(self):
        """Create test stores, products, variants, and combos."""
        self.client = APIClient()

        # Create stores. The owner is staff because the dashboard combo screens
        # run as authenticated admins — that is what lets them see inactive
        # combos (StoreComboViewSet.get_queryset hides inactive from non-staff).
        self.owner = User.objects.create_user(
            username='store-owner',
            password='testpass123',
            is_staff=True,
        )
        self.store1 = Store.objects.create(
            name='Store 1',
            slug='store-1',
            owner=self.owner,
            status='active'
        )
        self.store2 = Store.objects.create(
            name='Store 2',
            slug='store-2',
            owner=self.owner,
            status='active'
        )

        # Create products for store1
        self.product_rondelli = StoreProduct.objects.create(
            store=self.store1,
            name='Rondelli',
            slug='rondelli',
            price=29.90,
            track_stock=True,
            stock_quantity=100
        )

        self.product_molho = StoreProduct.objects.create(
            store=self.store1,
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

        # Create combo for store1
        self.combo1 = StoreCombo.objects.create(
            store=self.store1,
            name='Compre 3 Leve 4',
            slug='compre-3-leve-4',
            price=Decimal('45.00'),
            compare_at_price=Decimal('59.90'),
            description='4 Rondelli a preço especial',
            is_active=True
        )

        # Create combo group
        self.group1 = ComboProductGroup.objects.create(
            combo=self.combo1,
            product=self.product_rondelli,
            is_required=True,
            min_selections=4,
            max_selections=4,
            allow_duplicate_variants=True,
            position=0
        )

        # Create variant limits
        ComboProductGroupVariantLimit.objects.create(
            group=self.group1,
            variant=self.variant_rondelli_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=self.group1,
            variant=self.variant_rondelli_carne,
            max_selections=2
        )

        # Create inactive combo
        self.combo_inactive = StoreCombo.objects.create(
            store=self.store1,
            name='Combo Inativo',
            slug='combo-inativo',
            price=Decimal('30.00'),
            is_active=False
        )

        # Create combo for store2
        self.combo_store2 = StoreCombo.objects.create(
            store=self.store2,
            name='Combo Store 2',
            slug='combo-store2',
            price=Decimal('50.00'),
            is_active=True
        )

        self.client.force_authenticate(user=self.owner)

    def test_get_combo_detail_success(self):
        """Test successful retrieval of combo detail with groups and variants."""
        response = self.client.get(
            f'/api/v1/stores/combos/{self.combo1.id}/'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify basic info
        self.assertEqual(data['id'], str(self.combo1.id))
        self.assertEqual(data['name'], 'Compre 3 Leve 4')
        self.assertEqual(data['price'], '45.00')
        self.assertEqual(data['compare_at_price'], '59.90')
        self.assertEqual(data['is_active'], True)

        # Verify groups with variants
        self.assertEqual(len(data['groups']), 1)
        group = data['groups'][0]
        self.assertEqual(group['product_name'], 'Rondelli')
        self.assertEqual(group['min_selections'], 4)
        self.assertEqual(group['max_selections'], 4)
        self.assertEqual(group['allow_duplicate_variants'], True)

        # Verify variant limits
        self.assertEqual(len(group['variant_limits']), 2)
        variant_limit = group['variant_limits'][0]
        self.assertIn('variant_id', variant_limit)
        self.assertIn('variant_name', variant_limit)
        self.assertIn('stock', variant_limit)
        self.assertIn('max_selections', variant_limit)

    def test_get_combo_detail_with_store_filter(self):
        """Test that combo detail can be scoped with the ?store= filter."""
        response = self.client.get(
            f'/api/v1/stores/combos/{self.combo1.id}/?store={self.store1.slug}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['name'], 'Compre 3 Leve 4')

    def test_get_combo_detail_tenant_isolation_via_store_filter(self):
        """Combo from another store is not returned when scoped to store1."""
        # Scope the lookup to store1; store2's combo must not resolve.
        response = self.client.get(
            f'/api/v1/stores/combos/{self.combo_store2.id}/?store={self.store1.slug}'
        )
        self.assertEqual(response.status_code, 404)

    def test_get_combo_detail_not_found(self):
        """Test 404 when combo doesn't exist."""
        fake_id = uuid_module.uuid4()
        response = self.client.get(
            f'/api/v1/stores/combos/{fake_id}/'
        )
        self.assertEqual(response.status_code, 404)

    def test_get_combo_detail_invalid_combo_id(self):
        """Test 404 when combo_id is not a valid UUID."""
        response = self.client.get(
            '/api/v1/stores/combos/invalid-id/'
        )
        # Lookup by a non-UUID pk yields no row -> 404.
        self.assertEqual(response.status_code, 404)


class ComboListViewTestCase(APITestCase):
    """Tests for GET /api/v1/stores/combos/?store=<slug> (admin/dashboard route).

    This is the route pastita-dash actually calls (storesApi.getCombos passes
    the store slug as the ?store= query param). The viewset hides inactive
    combos from non-staff callers, so the admin client authenticates as staff.
    """

    def setUp(self):
        """Create test store with multiple combos."""
        self.client = APIClient()

        self.owner = User.objects.create_user(
            username='store-owner',
            password='testpass123',
            is_staff=True,
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store',
            owner=self.owner,
            status='active'
        )

        # Create active combos
        self.combo1 = StoreCombo.objects.create(
            store=self.store,
            name='Combo 1',
            slug='combo-1',
            price=Decimal('30.00'),
            is_active=True,
            sort_order=1
        )
        self.combo2 = StoreCombo.objects.create(
            store=self.store,
            name='Combo 2',
            slug='combo-2',
            price=Decimal('40.00'),
            is_active=True,
            sort_order=2
        )

        # Create inactive combo
        self.combo_inactive = StoreCombo.objects.create(
            store=self.store,
            name='Combo Inactive',
            slug='combo-inactive',
            price=Decimal('25.00'),
            is_active=False,
            sort_order=3
        )

        self.client.force_authenticate(user=self.owner)

    def test_list_combos_all(self):
        """Test listing all combos (active + inactive) for the store."""
        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Check pagination structure
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 3)

    def test_list_combos_filter_active(self):
        """Test listing only active combos."""
        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}&is_active=true'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 2)
        for combo in data['results']:
            self.assertTrue(combo['is_active'])

    def test_list_combos_filter_inactive(self):
        """Test listing only inactive combos."""
        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}&is_active=false'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertFalse(data['results'][0]['is_active'])

    def test_list_combos_pagination(self):
        """Test pagination with page_size parameter."""
        # Create more combos
        for i in range(3, 25):
            StoreCombo.objects.create(
                store=self.store,
                name=f'Combo {i}',
                slug=f'combo-{i}',
                price=Decimal('30.00'),
                is_active=True
            )

        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}&page_size=10'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 10)
        self.assertIsNotNone(data['next'])

    def test_list_combos_store_filter_isolation(self):
        """Combos are scoped to the requested store via ?store=."""
        other = Store.objects.create(
            name='Other Store',
            slug='other-store',
            owner=self.owner,
            status='active',
        )
        StoreCombo.objects.create(
            store=other, name='Other Combo', slug='other-combo',
            price=Decimal('10.00'), is_active=True,
        )
        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}'
        )
        self.assertEqual(response.status_code, 200)
        # Only this store's combos, not the other store's.
        self.assertEqual(len(response.json()['results']), 3)

    def test_list_combos_includes_groups(self):
        """Test that each combo exposes its groups structure."""
        response = self.client.get(
            f'/api/v1/stores/combos/?store={self.store.slug}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        combo = data['results'][0]
        self.assertIn('groups', combo)
        self.assertEqual(combo['groups'], [])  # Our test combos have no groups


class AddComboToCartViewTestCase(APITestCase):
    """Tests for POST /api/v1/stores/{store_slug}/cart/add-combo/"""

    def setUp(self):
        """Create test store, products, combo, and variants."""
        self.client = APIClient()

        self.owner = User.objects.create_user(
            username='store-owner',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store',
            owner=self.owner,
            status='active'
        )

        # Create product and variants
        self.product_rondelli = StoreProduct.objects.create(
            store=self.store,
            name='Rondelli',
            slug='rondelli',
            price=29.90,
            track_stock=True,
            stock_quantity=100
        )

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

        # Create combo with group
        self.combo = StoreCombo.objects.create(
            store=self.store,
            name='Compre 3 Leve 4',
            slug='compre-3-leve-4',
            price=Decimal('45.00'),
            is_active=True
        )

        self.group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product_rondelli,
            is_required=True,
            min_selections=4,
            max_selections=4,
            allow_duplicate_variants=True,
            position=0
        )

        ComboProductGroupVariantLimit.objects.create(
            group=self.group,
            variant=self.variant_frango,
            max_selections=2
        )
        ComboProductGroupVariantLimit.objects.create(
            group=self.group,
            variant=self.variant_carne,
            max_selections=2
        )

    def test_add_combo_to_cart_success(self):
        """Test successfully adding combo with valid selections."""
        # Use session-based cart
        self.client.get(f'/api/v1/stores/{self.store.slug}/')  # Initialize session

        selections = {
            str(self.group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),
                str(self.variant_carne.id),
                str(self.variant_carne.id),
            ]
        }

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': selections
            },
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify cart response
        self.assertIn('cart_id', data)
        self.assertIn('item_count', data)
        self.assertIn('subtotal', data)
        self.assertIn('items', data)
        self.assertEqual(data['item_count'], 1)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['quantity'], 1)
        self.assertEqual(data['items'][0]['combo_name'], 'Compre 3 Leve 4')

    def test_add_combo_to_cart_authenticated_user(self):
        """Test adding combo to cart as authenticated user."""
        user = User.objects.create_user(
            username='customer',
            password='testpass123'
        )
        self.client.force_authenticate(user=user)

        selections = {
            str(self.group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),
                str(self.variant_carne.id),
                str(self.variant_carne.id),
            ]
        }

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 2,
                'selections': selections
            },
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['item_count'], 2)

        # Verify cart persists for user
        cart = StoreCart.objects.get(store=self.store, user=user, is_active=True)
        self.assertEqual(cart.combo_items.count(), 1)

    def test_add_combo_to_cart_validation_fails_min_selections(self):
        """Test validation fails when min_selections not met."""
        selections = {
            str(self.group.id): [
                str(self.variant_frango.id),  # Only 1 selection, need 4
            ]
        }

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': selections
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('errors', data)
        self.assertGreater(len(data['errors']), 0)
        self.assertIn('mínimo', data['errors'][0].lower())

    def test_add_combo_to_cart_validation_fails_max_selections(self):
        """Test validation fails when max_selections exceeded."""
        selections = {
            str(self.group.id): [
                str(self.variant_frango.id),
                str(self.variant_frango.id),
                str(self.variant_frango.id),  # 3x frango, max is 2
                str(self.variant_carne.id),
            ]
        }

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': selections
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('errors', data)

    def test_add_combo_to_cart_combo_not_found(self):
        """Test 404 when combo doesn't exist."""
        fake_id = uuid_module.uuid4()
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(fake_id),
                'quantity': 1,
                'selections': {}
            },
            format='json'
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], 'Combo não encontrado.')

    def test_add_combo_to_cart_store_not_found(self):
        """Test 404 when store doesn't exist."""
        response = self.client.post(
            '/api/v1/stores/fake-store/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': {}
            },
            format='json'
        )

        self.assertEqual(response.status_code, 404)

    def test_add_combo_to_cart_invalid_quantity(self):
        """Test 400 with invalid quantity."""
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 0,
                'selections': {}
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Quantidade', response.json()['detail'])

    def test_add_combo_to_cart_missing_combo_id(self):
        """Test 400 when combo_id is missing."""
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'quantity': 1,
                'selections': {}
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('combo_id', response.json()['detail'])

    def test_add_combo_to_cart_tenant_isolation(self):
        """Test that combo from other store cannot be added."""
        other_store = Store.objects.create(
            name='Other Store',
            slug='other-store',
            owner=self.owner,
            status='active'
        )

        # Create combo in other store
        other_combo = StoreCombo.objects.create(
            store=other_store,
            name='Other Combo',
            slug='other-combo',
            price=Decimal('50.00'),
            is_active=True
        )

        # Try to add other_combo via self.store
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(other_combo.id),
                'quantity': 1,
                'selections': {}
            },
            format='json'
        )

        self.assertEqual(response.status_code, 404)


class ComboCartIntegrationTestCase(APITestCase):
    """Integration tests for combo cart interactions."""

    def setUp(self):
        """Create test setup."""
        self.client = APIClient()

        self.owner = User.objects.create_user(
            username='store-owner',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='test-store',
            owner=self.owner,
            status='active'
        )

        # Create product and variants
        self.product = StoreProduct.objects.create(
            store=self.store,
            name='Pizza',
            slug='pizza',
            price=29.90,
            track_stock=True,
            stock_quantity=100
        )

        self.variant1 = StoreProductVariant.objects.create(
            product=self.product,
            name='Pequena',
            stock_quantity=50
        )
        self.variant2 = StoreProductVariant.objects.create(
            product=self.product,
            name='Grande',
            stock_quantity=50
        )

        # Create combo
        self.combo = StoreCombo.objects.create(
            store=self.store,
            name='Pizza Combo',
            slug='pizza-combo',
            price=Decimal('50.00'),
            is_active=True
        )

        # Create group
        self.group = ComboProductGroup.objects.create(
            combo=self.combo,
            product=self.product,
            is_required=True,
            min_selections=1,
            max_selections=1,
            position=0
        )

        ComboProductGroupVariantLimit.objects.create(
            group=self.group,
            variant=self.variant1,
            max_selections=1
        )
        ComboProductGroupVariantLimit.objects.create(
            group=self.group,
            variant=self.variant2,
            max_selections=1
        )

    def test_multiple_combos_in_cart(self):
        """Test adding multiple different combos to cart."""
        self.client.get(f'/api/v1/stores/{self.store.slug}/')  # Init session

        # Add first combo
        response1 = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': {
                    str(self.group.id): [str(self.variant1.id)]
                }
            },
            format='json'
        )

        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertEqual(data1['item_count'], 1)

        # Add same combo again with different selections
        response2 = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add-combo/',
            {
                'combo_id': str(self.combo.id),
                'quantity': 1,
                'selections': {
                    str(self.group.id): [str(self.variant2.id)]
                }
            },
            format='json'
        )

        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2['item_count'], 2)  # Both items in cart
