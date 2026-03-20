"""
Tests for the Public API — endpoints that require no authentication.
Used by the storefronts (pastita-3d, ce-saladas).
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.stores.models import Store, StoreCategory, StoreProduct

User = get_user_model()


def _make_owner():
    return User.objects.create_user(
        username='pub_owner', email='pub@example.com', password='testpass123'
    )


def _make_active_store(owner, slug='test-store'):
    return Store.objects.create(
        name='Test Store',
        slug=slug,
        store_type=Store.StoreType.FOOD,
        status=Store.StoreStatus.ACTIVE,
        owner=owner,
        currency='BRL',
    )


def _make_category(store, name='Burgers', slug='burgers'):
    return StoreCategory.objects.create(
        store=store, name=name, slug=slug, is_active=True, sort_order=1
    )


def _make_product(store, category, name='Classic Burger', slug='classic-burger', price=25.00):
    return StoreProduct.objects.create(
        store=store,
        category=category,
        name=name,
        slug=slug,
        price=price,
        status=StoreProduct.ProductStatus.ACTIVE,
        sort_order=1,
    )


class PublicApiNoAuthTestCase(TestCase):
    """All public endpoints must return data WITHOUT authentication."""

    def setUp(self):
        self.client = APIClient()
        owner = _make_owner()
        self.store = _make_active_store(owner)
        self.category = _make_category(self.store)
        self.product = _make_product(self.store, self.category)

    # --- Store detail ---

    def test_store_detail_no_auth(self):
        """GET /api/v1/public/{slug}/ returns 200 with no credentials."""
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['slug'], self.store.slug)

    def test_store_detail_contains_name(self):
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/')
        self.assertEqual(resp.data['name'], self.store.name)

    def test_store_detail_unknown_slug_returns_404(self):
        resp = self.client.get('/api/v1/public/nonexistent-slug/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- Inactive store ---

    def test_inactive_store_returns_404(self):
        owner2 = User.objects.create_user(
            username='owner2', email='o2@example.com', password='pass'
        )
        inactive = Store.objects.create(
            name='Inactive', slug='inactive-store',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.INACTIVE,
            owner=owner2, currency='BRL',
        )
        resp = self.client.get(f'/api/v1/public/{inactive.slug}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- Catalog ---

    def test_catalog_no_auth(self):
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/catalog/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('store', resp.data)
        self.assertIn('catalog', resp.data)

    def test_catalog_contains_categories_and_products(self):
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/catalog/')
        catalog = resp.data['catalog']
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]['slug'], self.category.slug)
        self.assertEqual(len(catalog[0]['products']), 1)
        self.assertEqual(catalog[0]['products'][0]['name'], self.product.name)

    def test_catalog_excludes_inactive_category(self):
        StoreCategory.objects.create(
            store=self.store, name='Hidden', slug='hidden', is_active=False
        )
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/catalog/')
        slugs = [c['slug'] for c in resp.data['catalog']]
        self.assertNotIn('hidden', slugs)

    def test_catalog_excludes_inactive_products(self):
        StoreProduct.objects.create(
            store=self.store, category=self.category,
            name='Draft Product', slug='draft-product', price=10.00,
            status=StoreProduct.ProductStatus.INACTIVE,
        )
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/catalog/')
        names = [p['name'] for p in resp.data['catalog'][0]['products']]
        self.assertNotIn('Draft Product', names)

    # --- Categories ---

    def test_categories_no_auth(self):
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/categories/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)
        self.assertEqual(resp.data[0]['slug'], self.category.slug)

    def test_categories_excludes_inactive(self):
        StoreCategory.objects.create(
            store=self.store, name='Hidden', slug='hidden-cat', is_active=False
        )
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/categories/')
        slugs = [c['slug'] for c in resp.data]
        self.assertNotIn('hidden-cat', slugs)

    # --- Products ---

    def test_products_no_auth(self):
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/products/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)
        self.assertEqual(len(resp.data), 1)

    def test_products_filter_by_category(self):
        other_cat = _make_category(self.store, name='Drinks', slug='drinks')
        _make_product(self.store, other_cat, name='Coke', slug='coke', price=5.00)

        resp = self.client.get(
            f'/api/v1/public/{self.store.slug}/products/?category={other_cat.slug}'
        )
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], 'Coke')

    def test_products_search(self):
        _make_product(self.store, self.category, name='Veggie Wrap', slug='veggie-wrap', price=18.00)

        resp = self.client.get(
            f'/api/v1/public/{self.store.slug}/products/?search=Veggie'
        )
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], 'Veggie Wrap')

    def test_products_excludes_inactive(self):
        StoreProduct.objects.create(
            store=self.store, category=self.category,
            name='Draft', slug='draft', price=5.00,
            status=StoreProduct.ProductStatus.INACTIVE,
        )
        resp = self.client.get(f'/api/v1/public/{self.store.slug}/products/')
        names = [p['name'] for p in resp.data]
        self.assertNotIn('Draft', names)

    # --- Product detail ---

    def test_product_detail_no_auth(self):
        resp = self.client.get(
            f'/api/v1/public/{self.store.slug}/products/{self.product.pk}/'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], self.product.name)

    def test_product_detail_wrong_store_returns_404(self):
        """Product from store A must not be accessible via store B's public URL."""
        owner2 = User.objects.create_user(
            username='store2owner', email='s2@example.com', password='pass'
        )
        store2 = _make_active_store(owner2, slug='store-b')
        resp = self.client.get(
            f'/api/v1/public/{store2.slug}/products/{self.product.pk}/'
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_detail_inactive_returns_404(self):
        inactive_p = StoreProduct.objects.create(
            store=self.store, category=self.category,
            name='Hidden Product', slug='hidden-product', price=99.00,
            status=StoreProduct.ProductStatus.INACTIVE,
        )
        resp = self.client.get(
            f'/api/v1/public/{self.store.slug}/products/{inactive_p.pk}/'
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
