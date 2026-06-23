"""
Tests for the aggregated customer KPIs endpoint.

GET /api/v1/stores/customers/stats/?store=<slug-or-uuid>
returns server-side aggregates so the dashboard CustomersPage doesn't have to
download 500 customers and compute KPIs in JS.

Contract:
{ "total": <int>, "active": <int>, "with_orders": <int>, "total_revenue": "<decimal string>" }

The route is the global DRF router route /api/v1/stores/customers/
(see apps/stores/urls.py line ~131). Store scoping comes from the viewset's
get_queryset (StoreQuerysetMixin + ?store=), so a second store's customers must
NOT leak into the aggregate (tenant isolation).
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from apps.stores.models import Store, StoreCustomer

User = get_user_model()


class CustomerStatsActionTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.owner = User.objects.create_user(
            username='stats-owner',
            password='testpass123',
        )

        self.store1 = Store.objects.create(
            name='Store 1',
            slug='store-1',
            owner=self.owner,
            status='active',
        )
        self.store2 = Store.objects.create(
            name='Store 2',
            slug='store-2',
            owner=self.owner,
            status='active',
        )

        # --- Store 1 customers (the scope under test) ---
        # active + has orders + spent
        self._make_customer(self.store1, 'a@s1.com', total_orders=3,
                            total_spent=Decimal('100.50'), is_active=True)
        # active + has orders + spent
        self._make_customer(self.store1, 'b@s1.com', total_orders=1,
                            total_spent=Decimal('50.25'), is_active=True)
        # inactive + no orders + no spent
        self._make_customer(self.store1, 'c@s1.com', total_orders=0,
                            total_spent=Decimal('0.00'), is_active=False)
        # store1 expected:
        #   total = 3, active = 2, with_orders = 2, revenue = 150.75

        # --- Store 2 customers (must NOT be counted) ---
        self._make_customer(self.store2, 'x@s2.com', total_orders=99,
                            total_spent=Decimal('9999.99'), is_active=True)
        self._make_customer(self.store2, 'y@s2.com', total_orders=5,
                            total_spent=Decimal('500.00'), is_active=True)

    def _make_customer(self, store, email, total_orders, total_spent, is_active):
        user = User.objects.create_user(username=email, email=email,
                                        password='x')
        return StoreCustomer.objects.create(
            store=store,
            user=user,
            total_orders=total_orders,
            total_spent=total_spent,
            is_active=is_active,
        )

    def test_stats_returns_correct_aggregates_for_scoped_store(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            '/api/v1/stores/customers/stats/',
            {'store': self.store1.slug},
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['active'], 2)
        self.assertEqual(data['with_orders'], 2)
        self.assertEqual(data['total_revenue'], '150.75')

    def test_stats_tenant_isolation_second_store_not_counted(self):
        """Store 2 customers (huge numbers) must never bleed into store 1."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            '/api/v1/stores/customers/stats/',
            {'store': self.store1.slug},
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        # store2 had 99+5 orders and ~10499.99 revenue — none of it here
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['total_revenue'], '150.75')

        # And querying store2 directly yields its own (different) numbers.
        response2 = self.client.get(
            '/api/v1/stores/customers/stats/',
            {'store': self.store2.slug},
        )
        data2 = response2.json()
        self.assertEqual(data2['total'], 2)
        self.assertEqual(data2['active'], 2)
        self.assertEqual(data2['with_orders'], 2)
        self.assertEqual(data2['total_revenue'], '10499.99')

    def test_stats_zero_revenue_string_when_empty(self):
        empty_store = Store.objects.create(
            name='Empty', slug='empty-store', owner=self.owner, status='active',
        )
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            '/api/v1/stores/customers/stats/',
            {'store': empty_store.slug},
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['active'], 0)
        self.assertEqual(data['with_orders'], 0)
        self.assertEqual(data['total_revenue'], '0.00')
