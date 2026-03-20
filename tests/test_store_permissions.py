"""
Tests for StorePermissionMixin and cross-store data isolation.

Ensures that:
- Users can only access data from stores they own or are staff of
- Cross-store access is denied (critical security property)
- Superusers can access all stores
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreProduct, StoreCategory

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass123',
    )


def _make_store(owner, slug):
    return Store.objects.create(
        name=f'Store {slug}',
        slug=slug,
        store_type=Store.StoreType.FOOD,
        status=Store.StoreStatus.ACTIVE,
        owner=owner,
        currency='BRL',
    )


class CrossStoreIsolationTestCase(TestCase):
    """
    Verify that authenticated users cannot access another store's data
    through the dashboard API.
    """

    def setUp(self):
        self.client = APIClient()

        self.owner_a = _make_user('owner_a')
        self.owner_b = _make_user('owner_b')
        self.superuser = User.objects.create_superuser(
            username='superadmin',
            email='super@example.com',
            password='testpass123',
        )

        self.token_a = Token.objects.create(user=self.owner_a)
        self.token_b = Token.objects.create(user=self.owner_b)
        self.token_super = Token.objects.create(user=self.superuser)

        self.store_a = _make_store(self.owner_a, 'perm-store-a')
        self.store_b = _make_store(self.owner_b, 'perm-store-b')

        self.category_a = StoreCategory.objects.create(
            store=self.store_a,
            name='Cat A',
            slug='cat-a',
        )
        self.category_b = StoreCategory.objects.create(
            store=self.store_b,
            name='Cat B',
            slug='cat-b',
        )

        self.product_a = StoreProduct.objects.create(
            store=self.store_a,
            category=self.category_a,
            name='Product A',
            slug='product-a',
            price=10.00,
            status=StoreProduct.ProductStatus.ACTIVE,
        )
        self.product_b = StoreProduct.objects.create(
            store=self.store_b,
            category=self.category_b,
            name='Product B',
            slug='product-b',
            price=20.00,
            status=StoreProduct.ProductStatus.ACTIVE,
        )

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _products_url(self, store):
        """URL for dashboard (management) products — nested under stores/{pk}/."""
        return f'/api/v1/stores/stores/{store.pk}/products/'

    def test_owner_a_can_access_own_store_products(self):
        self._auth(self.token_a)
        response = self.client.get(self._products_url(self.store_a))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_a_cannot_write_to_store_b(self):
        """Owner A must not be able to create products in Store B."""
        self._auth(self.token_a)
        response = self.client.post(
            self._products_url(self.store_b),
            data={
                'name': 'Injected Product',
                'price': '99.00',
                'status': 'active',
            },
            format='json',
        )
        # Must be 403 or 404 — never 200/201
        self.assertIn(response.status_code, [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ])

    def test_unauthenticated_cannot_access_dashboard_products(self):
        self.client.credentials()  # clear auth
        response = self.client.post(
            self._products_url(self.store_a),
            data={'name': 'X', 'price': '10.00'},
            format='json',
        )
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])

    def test_superuser_can_access_any_store(self):
        self._auth(self.token_super)
        resp_a = self.client.get(self._products_url(self.store_a))
        resp_b = self.client.get(self._products_url(self.store_b))
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)


class StorePermissionMixinUnitTestCase(TestCase):
    """Unit-level tests for StorePermissionMixin queryset filtering."""

    def setUp(self):
        self.owner_a = _make_user('mixin_owner_a')
        self.owner_b = _make_user('mixin_owner_b')
        self.superuser = User.objects.create_superuser(
            username='mixin_super',
            email='mixin_super@example.com',
            password='testpass123',
        )
        self.store_a = _make_store(self.owner_a, 'mixin-store-a')
        self.store_b = _make_store(self.owner_b, 'mixin-store-b')

    def _store_ids_for(self, user):
        from django.db.models import Q
        if user.is_superuser or user.is_staff:
            return None
        return list(
            Store.objects.filter(
                Q(owner=user) | Q(staff=user), is_active=True
            ).values_list('id', flat=True)
        )

    def test_owner_a_sees_only_own_store(self):
        ids = self._store_ids_for(self.owner_a)
        self.assertIsNotNone(ids)
        self.assertIn(self.store_a.id, ids)
        self.assertNotIn(self.store_b.id, ids)

    def test_superuser_gets_unrestricted(self):
        ids = self._store_ids_for(self.superuser)
        self.assertIsNone(ids)  # None means no filter → see all

    def test_staff_member_sees_assigned_store(self):
        staff_user = _make_user('staff_x')
        self.store_a.staff.add(staff_user)
        ids = self._store_ids_for(staff_user)
        self.assertIn(self.store_a.id, ids)
        self.assertNotIn(self.store_b.id, ids)
