from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreDeliveryZone,
    StoreOrder,
    StoreOrderItem,
    StoreProduct,
)


User = get_user_model()


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class StorefrontSmokeContractTests(APITestCase):
    """Smoke coverage for the critical customer-facing contracts in the roadmap."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='smoke-owner',
            email='owner@example.com',
            password='unused-test-password',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Cê Saladas',
            slug='ce-saladas-smoke',
            status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
            email='loja@example.com',
            phone='63999999999',
            whatsapp_number='5563999999999',
            min_order_value=Decimal('0.00'),
            default_delivery_fee=Decimal('7.00'),
            latitude=Decimal('-10.1840000'),
            longitude=Decimal('-48.3330000'),
        )
        self.category = StoreCategory.objects.create(
            store=self.store,
            name='Saladas',
            slug='saladas',
            is_active=True,
            sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Salada Caesar',
            slug='salada-caesar',
            price=Decimal('29.90'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
            stock_quantity=10,
        )

    def test_store_catalog_contract_returns_canonical_fields(self):
        response = self.client.get(f'/api/v1/stores/{self.store.slug}/catalog/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn('store', payload)
        self.assertIn('categories', payload)
        self.assertIn('products', payload)
        self.assertIn('combos', payload)
        self.assertIn('products_by_category', payload)
        self.assertEqual(payload['store']['slug'], self.store.slug)
        self.assertTrue(any(item['slug'] == self.category.slug for item in payload['categories']))
        self.assertTrue(any(item['slug'] == self.product.slug for item in payload['products']))

    def test_public_catalog_contract_returns_mobile_shape(self):
        response = self.client.get(f'/api/v1/public/{self.store.slug}/catalog/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['store']['slug'], self.store.slug)
        self.assertIn('catalog', payload)
        self.assertEqual(payload['catalog'][0]['slug'], self.category.slug)
        self.assertEqual(payload['catalog'][0]['products'][0]['slug'], self.product.slug)

    def test_checkout_creates_guest_order_and_by_token_can_read_it(self):
        cart_key = 'smoke-cart-key'
        cart = StoreCart.objects.create(store=self.store, session_key=cart_key)
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=2)

        checkout_response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            {
                'customer_name': 'Cliente Smoke',
                'customer_email': 'smoke@example.com',
                'customer_phone': '+5563999999999',
                'delivery_method': 'pickup',
                'payment_method': '',
                'customer_notes': 'Contrato smoke',
            },
            format='json',
            HTTP_X_CART_KEY=cart_key,
        )

        self.assertEqual(checkout_response.status_code, status.HTTP_201_CREATED)
        checkout_payload = checkout_response.json()
        self.assertIn('order_id', checkout_payload)
        self.assertIn('access_token', checkout_payload)
        self.assertEqual(checkout_payload['items'][0]['product_name'], self.product.name)

        detail_response = self.client.get(
            f"/api/v1/stores/orders/by-token/{checkout_payload['access_token']}/"
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload['order_id'], checkout_payload['order_id'])
        self.assertEqual(detail_payload['items'][0]['product_name'], self.product.name)

    def test_customer_order_detail_accepts_token_query(self):
        order = StoreOrder.objects.create(
            store=self.store,
            order_number='SMOKE-0001',
            customer_name='Cliente Smoke',
            customer_email='smoke@example.com',
            customer_phone='+5563999999999',
            subtotal=Decimal('29.90'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('29.90'),
            delivery_method=StoreOrder.DeliveryMethod.PICKUP,
            payment_method='pix',
        )
        StoreOrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            unit_price=Decimal('29.90'),
            quantity=1,
            subtotal=Decimal('29.90'),
        )

        response = self.client.get(
            f'/api/v1/stores/customer/orders/{order.id}/',
            {'token': order.access_token},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload['id'], str(order.id))
        self.assertEqual(payload['items'][0]['product_name'], self.product.name)

    @patch('apps.stores.api.views.storefront_views.checkout_service.calculate_delivery_fee')
    def test_delivery_fee_contract_normalizes_backend_quote(self, calculate_delivery_fee):
        calculate_delivery_fee.return_value = {
            'available': True,
            'fee': Decimal('9.50'),
            'distance_km': Decimal('4.2'),
            'duration_minutes': 12,
            'source': 'fixed_zone',
        }

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {'distance_km': '4.2'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload['available'])
        self.assertEqual(Decimal(str(payload['fee'])), Decimal('9.50'))
        self.assertEqual(Decimal(str(payload['distance_km'])), Decimal('4.2'))

    def test_delivery_fee_real_zone_palmas_inner_ring(self):
        StoreDeliveryZone.objects.create(
            store=self.store,
            name='Palmas até 5km',
            zone_type='custom_distance',
            min_km=Decimal('0'),
            max_km=Decimal('5'),
            delivery_fee=Decimal('6.00'),
            is_active=True,
        )
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {'distance_km': '3.5'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload['available'])
        self.assertEqual(Decimal(str(payload['fee'])), Decimal('6.00'))
        self.assertEqual(payload['zone_name'], 'Palmas até 5km')

    def test_delivery_fee_out_of_area_returns_unavailable(self):
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {'distance_km': '25.0'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertFalse(payload['available'])
        self.assertIsNone(payload.get('fee'))

    def test_payment_status_by_token_returns_order_status(self):
        """Flutter polls /orders/<uuid>/payment-status/?token= after checkout."""
        order = StoreOrder.objects.create(
            store=self.store,
            order_number='SMOKE-PAY-0001',
            customer_name='Cliente Smoke',
            customer_email='smoke@example.com',
            customer_phone='+5563999999999',
            subtotal=Decimal('29.90'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('29.90'),
            delivery_method=StoreOrder.DeliveryMethod.PICKUP,
            payment_method='pix',
        )
        StoreOrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            unit_price=Decimal('29.90'),
            quantity=1,
            subtotal=Decimal('29.90'),
        )

        response = self.client.get(
            f'/api/v1/stores/orders/{order.id}/payment-status/',
            {'token': order.access_token},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn('status', payload)
        self.assertIn('payment_status', payload)
        self.assertEqual(payload['items'][0]['product_name'], self.product.name)

    def test_orders_uuid_direct_path_requires_auth_admin_only(self):
        """Guard: /api/v1/stores/orders/<uuid>/ is the admin ViewSet route.
        Unauthenticated mobile clients must NOT use it — they get 401/403.
        Mobile paths: orders/by-token/<token>/ or customer/orders/<uuid>/?token=
        """
        order = StoreOrder.objects.create(
            store=self.store,
            order_number='SMOKE-GUARD-0001',
            customer_name='Cliente Guard',
            customer_email='guard@example.com',
            customer_phone='+5563999999999',
            subtotal=Decimal('29.90'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('29.90'),
            delivery_method=StoreOrder.DeliveryMethod.PICKUP,
            payment_method='pix',
        )

        response = self.client.get(f'/api/v1/stores/orders/{order.id}/')

        self.assertIn(response.status_code, (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ))


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class DeliveryZoneContractTest(APITestCase):
    """Contrato de zona de entrega: endpoint real POST /api/v1/stores/{slug}/delivery-fee/"""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='dz-contract-owner',
            email='dz-owner@example.com',
            password='unused-test-password',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='DZ Contract Store',
            slug='dz-contract-store',
            status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
            email='dz@example.com',
            phone='63999999998',
            whatsapp_number='5563999999998',
            min_order_value=Decimal('0.00'),
            default_delivery_fee=Decimal('7.00'),
            latitude=Decimal('-10.1840000'),
            longitude=Decimal('-48.3330000'),
        )
        StoreDeliveryZone.objects.create(
            store=self.store,
            name='Zona 5km',
            zone_type='custom_distance',
            min_km=Decimal('0'),
            max_km=Decimal('5'),
            delivery_fee=Decimal('6.00'),
            is_active=True,
        )

    def test_within_range_returns_fee(self):
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {'distance_km': 3.0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertTrue(payload['available'])
        self.assertGreater(float(payload['fee']), 0)

    def test_out_of_range_returns_unavailable(self):
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {'distance_km': 25.0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertFalse(payload['available'])

    def test_missing_location_returns_400(self):
        """Empty payload without any location info must return 400, not a default fee."""
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/delivery-fee/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class FlutterCheckoutContractTest(APITestCase):
    """Contrato de checkout Flutter: payload realista cria pedido com order_number."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='flutter-contract-owner',
            email='flutter-owner@example.com',
            password='unused-test-password',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Flutter Contract Store',
            slug='flutter-contract-store',
            status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
            email='flutter@example.com',
            phone='63999999997',
            whatsapp_number='5563999999997',
            min_order_value=Decimal('0.00'),
            default_delivery_fee=Decimal('0.00'),
            latitude=Decimal('-10.1840000'),
            longitude=Decimal('-48.3330000'),
        )
        category = StoreCategory.objects.create(
            store=self.store,
            name='Categoria Flutter',
            slug='cat-flutter',
            is_active=True,
            sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store,
            category=category,
            name='Produto Flutter',
            slug='produto-flutter',
            price=Decimal('19.90'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
            stock_quantity=10,
        )

    @patch('apps.stores.api.views.storefront_views.checkout_service.create_payment')
    def test_guest_checkout_accepts_flutter_payload(self, mock_create_payment):
        mock_create_payment.return_value = {'success': True, 'payment_id': 'test'}

        cart_key = 'flutter-contract-cart-key'
        cart = StoreCart.objects.create(store=self.store, session_key=cart_key)
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=1)

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            {
                'items': [{'product_id': str(self.product.id), 'quantity': 1}],
                'delivery_method': 'pickup',
                'customer_name': 'Test Flutter',
                'customer_email': 'flutter@test.com',
                'customer_phone': '+5563999990099',
                'payment_method': 'pix',
            },
            format='json',
            HTTP_X_CART_KEY=cart_key,
        )

        self.assertIn(response.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))
        payload = response.json()
        self.assertIn('order_number', payload)
