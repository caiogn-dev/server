from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.sse_views import OrderSSEView
from apps.stores.consumers import user_can_access_customer_order, user_can_access_store_orders
from apps.stores.models import Store, StoreOrder


User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass123',
    )


def make_store(owner, slug):
    return Store.objects.create(
        owner=owner,
        name=f'Store {slug}',
        slug=slug,
        store_type=Store.StoreType.FOOD,
        status=Store.StoreStatus.ACTIVE,
        is_active=True,
    )


def make_order(store, number):
    return StoreOrder.objects.create(
        store=store,
        customer_name='Cliente',
        customer_email=f'{number}@example.com',
        customer_phone='556399999999',
        subtotal=Decimal('10.00'),
        discount=Decimal('0.00'),
        tax=Decimal('0.00'),
        delivery_fee=Decimal('0.00'),
        total=Decimal('10.00'),
    )


class RealtimeAccessTests(TestCase):
    def setUp(self):
        self.owner_a = make_user('rt-owner-a')
        self.owner_b = make_user('rt-owner-b')
        self.staff = make_user('rt-staff')
        self.store_a = make_store(self.owner_a, 'rt-store-a')
        self.store_b = make_store(self.owner_b, 'rt-store-b')
        self.store_a.staff.add(self.staff)
        self.order_a = make_order(self.store_a, 'order-a')
        self.order_b = make_order(self.store_b, 'order-b')

    def test_order_websocket_requires_store_access(self):
        allowed = user_can_access_store_orders(self.owner_a, self.store_b.slug)

        self.assertFalse(allowed)

    def test_order_websocket_allows_store_staff(self):
        allowed = user_can_access_store_orders(self.staff, self.store_a.slug)

        self.assertTrue(allowed)

    def test_order_websocket_rejects_anonymous_active_store(self):
        from django.contrib.auth.models import AnonymousUser

        allowed = user_can_access_store_orders(AnonymousUser(), self.store_a.slug)

        self.assertFalse(allowed)

    def test_order_sse_queryset_is_scoped_to_accessible_stores(self):
        queryset = OrderSSEView()._accessible_orders_queryset(self.owner_a)

        self.assertIn(self.order_a, queryset)
        self.assertNotIn(self.order_b, queryset)

    def test_order_sse_requested_store_cannot_escape_accessible_scope(self):
        view = OrderSSEView()
        queryset = view._accessible_orders_queryset(self.owner_a)
        scoped = view._filter_requested_scope(queryset, store_id=self.store_b.slug)

        self.assertFalse(scoped.exists())

    def test_customer_order_websocket_requires_access_token_for_public_user(self):
        from django.contrib.auth.models import AnonymousUser

        allowed = user_can_access_customer_order(AnonymousUser(), str(self.order_a.id))

        self.assertFalse(allowed)

    def test_customer_order_websocket_allows_valid_access_token(self):
        from django.contrib.auth.models import AnonymousUser

        allowed = user_can_access_customer_order(
            AnonymousUser(),
            str(self.order_a.id),
            self.order_a.access_token,
        )

        self.assertTrue(allowed)

    def test_customer_order_websocket_allows_store_owner_without_public_token(self):
        allowed = user_can_access_customer_order(self.owner_a, str(self.order_a.id))

        self.assertTrue(allowed)
