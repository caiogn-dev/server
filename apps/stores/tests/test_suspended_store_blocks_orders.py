"""
TDD Task 5 — Enforcement: loja suspensa não aceita pedido no storefront.

Testa:
  1. Helper puro `billing.store_accepts_orders(store)`
  2. Integração: endpoint POST /checkout/ retorna 403 para loja suspensa
                 e 201 para loja isenta (billing_exempt) mesmo suspensa.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.stores import billing
from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreProduct,
    StoreSubscription,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helper puro
# ---------------------------------------------------------------------------

class StoreAcceptsOrdersTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username='billing-helper-owner',
            email='helper@task5.com',
            password='unused',
        )

    def _store(self, slug, **kwargs):
        return Store.objects.create(owner=self.owner, name=slug, slug=slug, **kwargs)

    def test_store_without_subscription_accepts(self):
        store = self._store('a')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_suspended_store_rejects(self):
        store = self._store('b')
        StoreSubscription.objects.create(store=store, status='suspended')
        self.assertFalse(billing.store_accepts_orders(store))

    def test_suspended_but_exempt_accepts(self):
        store = self._store('c', billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='suspended')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_active_store_accepts(self):
        store = self._store('d')
        StoreSubscription.objects.create(store=store, status='active')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_trialing_store_accepts(self):
        store = self._store('e')
        StoreSubscription.objects.create(store=store, status='trialing')
        self.assertTrue(billing.store_accepts_orders(store))

    def test_past_due_store_accepts(self):
        """past_due ainda aceita pedidos (apenas suspended bloqueia)."""
        store = self._store('f')
        StoreSubscription.objects.create(store=store, status='past_due')
        self.assertTrue(billing.store_accepts_orders(store))


# ---------------------------------------------------------------------------
# Integração: endpoint de checkout
# ---------------------------------------------------------------------------

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
class SuspendedStoreCheckoutTest(APITestCase):
    """Loja suspensa → checkout retorna 403; isenção curto-circuita o bloqueio."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='billing-owner-task5',
            email='owner-task5@example.com',
            password='unused',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Loja Suspensa',
            slug='loja-suspensa-task5',
            status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
            email='loja@task5.com',
            phone='63999990000',
            whatsapp_number='5563999990000',
            min_order_value=Decimal('0.00'),
            default_delivery_fee=Decimal('0.00'),
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-task5', is_active=True, sort_order=1
        )
        self.product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Produto Task5',
            slug='produto-task5',
            price=Decimal('10.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
            stock_quantity=99,
        )

    # ------------------------------------------------------------------ helpers
    def _cart_key(self):
        return 'task5-cart-key'

    def _create_cart_with_item(self):
        cart = StoreCart.objects.create(store=self.store, session_key=self._cart_key())
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=1)
        return cart

    def _checkout_payload(self):
        return {
            'customer_name': 'Cliente Task5',
            'customer_email': 'cli@task5.com',
            'customer_phone': '+5563999990001',
            'delivery_method': 'pickup',
            'payment_method': '',
        }

    # ------------------------------------------------------------------ testes
    def test_suspended_store_order_returns_403(self):
        StoreSubscription.objects.create(store=self.store, status='suspended')
        self._create_cart_with_item()

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('indisponível', response.json().get('detail', '').lower())

    def test_suspended_but_exempt_store_order_returns_201(self):
        self.store.billing_exempt = True
        self.store.save()
        StoreSubscription.objects.create(store=self.store, status='suspended')
        self._create_cart_with_item()

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_active_store_order_returns_201(self):
        StoreSubscription.objects.create(store=self.store, status='active')
        self._create_cart_with_item()

        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
