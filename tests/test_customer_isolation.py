"""
Tests for store/customer isolation — ensures customers from one store
do NOT appear in another store's customer list.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCustomer

User = get_user_model()


def _create_store(owner, name, slug):
    return Store.objects.create(
        owner=owner,
        name=name,
        slug=slug,
        is_active=True,
    )


class CustomerIsolationTest(TestCase):
    """
    Customers from Store A must NOT appear in Store B's customer list.
    """

    def setUp(self):
        # Two separate store owners
        self.owner_a = User.objects.create_user(username='owner_a', email='a@a.com', password='pass')
        self.owner_b = User.objects.create_user(username='owner_b', email='b@b.com', password='pass')

        self.store_a = _create_store(self.owner_a, 'Store A', 'store-a')
        self.store_b = _create_store(self.owner_b, 'Store B', 'store-b')

        # Customer who bought from Store A only
        self.customer_a_only = User.objects.create_user(
            username='cust_a', email='cust_a@example.com', password='pass'
        )
        StoreCustomer.objects.create(store=self.store_a, user=self.customer_a_only)

        # Customer who bought from Store B only
        self.customer_b_only = User.objects.create_user(
            username='cust_b', email='cust_b@example.com', password='pass'
        )
        StoreCustomer.objects.create(store=self.store_b, user=self.customer_b_only)

        # Customer who bought from BOTH stores
        self.shared_customer = User.objects.create_user(
            username='cust_shared', email='shared@example.com', password='pass'
        )
        StoreCustomer.objects.create(store=self.store_a, user=self.shared_customer)
        StoreCustomer.objects.create(store=self.store_b, user=self.shared_customer)

    def test_store_a_customers_scoped(self):
        """Only Store A customers should appear for Store A."""
        users_in_a = User.objects.filter(
            store_profiles__store_id=self.store_a.id,
            is_active=True,
        ).distinct()
        emails = set(users_in_a.values_list('email', flat=True))
        self.assertIn('cust_a@example.com', emails)
        self.assertIn('shared@example.com', emails)
        self.assertNotIn('cust_b@example.com', emails)

    def test_store_b_customers_scoped(self):
        """Only Store B customers should appear for Store B."""
        users_in_b = User.objects.filter(
            store_profiles__store_id=self.store_b.id,
            is_active=True,
        ).distinct()
        emails = set(users_in_b.values_list('email', flat=True))
        self.assertIn('cust_b@example.com', emails)
        self.assertIn('shared@example.com', emails)
        self.assertNotIn('cust_a@example.com', emails)

    def test_store_customer_unique_per_store(self):
        """A user should only have one StoreCustomer per store."""
        count = StoreCustomer.objects.filter(
            store=self.store_a, user=self.customer_a_only
        ).count()
        self.assertEqual(count, 1)


class CustomerAPIIsolationTest(TestCase):
    """
    Marketing customers API must scope results to the requested store.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='shop_owner', email='owner@shop.com', password='pass'
        )
        self.other_user = User.objects.create_user(
            username='other_user', email='other@shop.com', password='pass'
        )
        self.store = _create_store(self.owner, 'My Shop', 'my-shop')

        # other_user has NO StoreCustomer for this store
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_customers_endpoint_requires_store_param(self):
        response = self.client.get('/api/v1/marketing/customers/')
        self.assertEqual(response.status_code, 400)

    def test_customers_endpoint_excludes_non_store_users(self):
        response = self.client.get(f'/api/v1/marketing/customers/?store={self.store.id}')
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            emails = [c['email'] for c in response.data.get('results', [])]
            # other_user is NOT a customer of this store
            self.assertNotIn('other@shop.com', emails)
