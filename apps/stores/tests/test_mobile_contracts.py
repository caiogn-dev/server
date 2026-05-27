"""
Regression tests for mobile API contracts.

Covers:
- /api/v1/mobile/orders/by-token/{token}/ — shape completa com timestamps
- /api/v1/mobile/orders/{id}/ — auth por token query param
- /api/v1/mobile/orders/{id}/payment-status/ — polling de pagamento
- /api/v1/mobile/orders/ — lista autenticada
- CustomerOrderDetailView retorna timestamps de status e pix_expires_at
"""
from decimal import Decimal
from datetime import timedelta

from django.test import override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct, StoreCategory

User = get_user_model()

_SETTINGS = dict(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)


def _make_store(owner):
    return Store.objects.create(
        owner=owner,
        name='Mobile Test Store',
        slug='mobile-test-store',
        status=Store.StoreStatus.ACTIVE,
        store_type=Store.StoreType.FOOD,
        email='mobile@example.com',
        phone='63999999999',
        whatsapp_number='5563999999999',
        min_order_value=Decimal('0.00'),
        default_delivery_fee=Decimal('5.00'),
    )


def _make_order(store, **kwargs):
    defaults = dict(
        order_number='MOB-0001',
        customer_name='Mobile Cliente',
        customer_email='mobile@example.com',
        customer_phone='+5563999999999',
        subtotal=Decimal('39.90'),
        delivery_fee=Decimal('5.00'),
        total=Decimal('44.90'),
        delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
        payment_method='pix',
    )
    defaults.update(kwargs)
    return StoreOrder.objects.create(store=store, **defaults)


@override_settings(**_SETTINGS)
class MobileOrderByTokenContractTest(APITestCase):
    """GET /api/v1/mobile/orders/by-token/{token}/ — shape completa."""

    def setUp(self):
        self.owner = User.objects.create_user('mob-owner', 'mob@ex.com', 'pw')
        self.store = _make_store(self.owner)
        self.order = _make_order(self.store)

    def test_returns_200_with_valid_token(self):
        r = self.client.get(f'/api/v1/mobile/orders/by-token/{self.order.access_token}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_returns_404_with_invalid_token(self):
        r = self.client.get('/api/v1/mobile/orders/by-token/invalid-token-xyz/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_response_includes_required_fields(self):
        r = self.client.get(f'/api/v1/mobile/orders/by-token/{self.order.access_token}/')
        data = r.json()
        for field in ('order_id', 'order_number', 'status', 'payment_status',
                      'payment_method', 'total', 'items', 'created_at', 'updated_at'):
            self.assertIn(field, data, f'missing field: {field}')

    def test_response_includes_status_timestamps(self):
        now = timezone.now()
        self.order.confirmed_at = now
        self.order.preparing_at = now + timedelta(minutes=2)
        self.order.save(update_fields=['confirmed_at', 'preparing_at'])

        r = self.client.get(f'/api/v1/mobile/orders/by-token/{self.order.access_token}/')
        data = r.json()
        self.assertIn('confirmed_at', data)
        self.assertIn('preparing_at', data)
        self.assertIn('ready_at', data)
        self.assertIn('out_for_delivery_at', data)
        self.assertIn('picked_up_at', data)
        self.assertIsNotNone(data['confirmed_at'])
        self.assertIsNotNone(data['preparing_at'])

    def test_pix_method_returns_pix_fields(self):
        self.order.pix_code = 'pix-code-test-123'
        self.order.pix_expires_at = timezone.now() + timedelta(minutes=30)
        self.order.save(update_fields=['pix_code', 'pix_expires_at'])

        r = self.client.get(f'/api/v1/mobile/orders/by-token/{self.order.access_token}/')
        data = r.json()
        self.assertIn('pix_code', data)
        self.assertIn('pix_expires_at', data)
        self.assertEqual(data['pix_code'], 'pix-code-test-123')
        self.assertIsNotNone(data['pix_expires_at'])

    def test_scheduled_fields_returned(self):
        from datetime import date, time
        self.order.scheduled_date = date(2026, 6, 1)
        self.order.scheduled_time = '14:00'
        self.order.save(update_fields=['scheduled_date', 'scheduled_time'])

        r = self.client.get(f'/api/v1/mobile/orders/by-token/{self.order.access_token}/')
        data = r.json()
        self.assertIn('scheduled_date', data)
        self.assertIn('scheduled_time', data)
        self.assertEqual(data['scheduled_time'], '14:00')


@override_settings(**_SETTINGS)
class MobileOrderDetailContractTest(APITestCase):
    """GET /api/v1/mobile/orders/{id}/ — auth por token query param."""

    def setUp(self):
        self.owner = User.objects.create_user('mob-detail-owner', 'det@ex.com', 'pw')
        self.store = _make_store(self.owner)
        self.order = _make_order(self.store, order_number='MOB-DET-001')

    def test_token_query_param_grants_access(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/',
            {'token': self.order.access_token},
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()['id'], str(self.order.id))

    def test_wrong_token_is_denied(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/',
            {'token': 'wrong-token'},
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_token_no_auth_is_denied(self):
        r = self.client.get(f'/api/v1/mobile/orders/{self.order.id}/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_owner_can_access(self):
        # order.customer is the owner user
        self.order.customer = self.owner
        self.order.save(update_fields=['customer'])
        token, _ = Token.objects.get_or_create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        r = self.client.get(f'/api/v1/mobile/orders/{self.order.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_response_has_access_token_field(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/',
            {'token': self.order.access_token},
        )
        data = r.json()
        self.assertIn('access_token', data)
        self.assertEqual(data['access_token'], self.order.access_token)

    def test_response_includes_full_timestamp_set(self):
        now = timezone.now()
        self.order.preparing_at = now
        self.order.ready_at = now + timedelta(minutes=5)
        self.order.save(update_fields=['preparing_at', 'ready_at'])

        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/',
            {'token': self.order.access_token},
        )
        data = r.json()
        for ts in ('paid_at', 'confirmed_at', 'preparing_at', 'ready_at',
                   'out_for_delivery_at', 'shipped_at', 'delivered_at',
                   'picked_up_at', 'cancelled_at'):
            self.assertIn(ts, data, f'missing timestamp: {ts}')
        self.assertIsNotNone(data['preparing_at'])
        self.assertIsNotNone(data['ready_at'])


@override_settings(**_SETTINGS)
class MobilePaymentStatusContractTest(APITestCase):
    """GET /api/v1/mobile/orders/{id}/payment-status/ — polling de pagamento."""

    def setUp(self):
        self.owner = User.objects.create_user('mob-pay-owner', 'pay@ex.com', 'pw')
        self.store = _make_store(self.owner)
        self.order = _make_order(self.store, order_number='MOB-PAY-001')

    def test_token_grants_access_to_payment_status(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/payment-status/',
            {'token': self.order.access_token},
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_response_has_payment_status_field(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/payment-status/',
            {'token': self.order.access_token},
        )
        data = r.json()
        self.assertIn('payment_status', data)
        self.assertIn('status', data)

    def test_wrong_token_denied(self):
        r = self.client.get(
            f'/api/v1/mobile/orders/{self.order.id}/payment-status/',
            {'token': 'bad'},
        )
        self.assertIn(r.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))


@override_settings(**_SETTINGS)
class MobileOrderListContractTest(APITestCase):
    """GET /api/v1/mobile/orders/ — lista autenticada."""

    def setUp(self):
        self.owner = User.objects.create_user('mob-list-owner', 'list@ex.com', 'pw')
        self.store = _make_store(self.owner)
        self.token, _ = Token.objects.get_or_create(user=self.owner)
        self.order = _make_order(self.store, order_number='MOB-LIST-001',
                                 customer=self.owner,
                                 customer_email=self.owner.email)

    def test_unauthenticated_is_denied(self):
        r = self.client.get('/api/v1/mobile/orders/')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_authenticated_returns_own_orders(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        r = self.client.get('/api/v1/mobile/orders/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
