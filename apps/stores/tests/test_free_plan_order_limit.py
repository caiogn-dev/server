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
    StoreOrder,
    StoreProduct,
)

User = get_user_model()


class FreePlanOrderLimitTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o-fp', 'o-fp@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja Free', slug='loja-free', owner=self.owner,
            plan='free', status=Store.StoreStatus.ACTIVE)

    def test_helper_conta_mes_corrente(self):
        # within_order_limit usa o count passado; aqui validamos a semântica do cap.
        self.store.plan = 'free'
        self.assertFalse(billing.within_order_limit(self.store, 30))
        self.assertTrue(billing.within_order_limit(self.store, 0))


# ---------------------------------------------------------------------------
# Integração: endpoint de checkout (request real, mesmo padrão de
# test_suspended_store_blocks_orders.py)
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
class FreePlanOrderLimitCheckoutTest(APITestCase):
    """Loja free não-isenta com 30+ pedidos no mês → checkout retorna 400."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='billing-owner-free-limit',
            email='owner-free-limit@example.com',
            password='unused',
        )

    def _store(self, slug, **kwargs):
        defaults = dict(
            owner=self.owner,
            name=slug,
            slug=slug,
            status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
            email=f'{slug}@example.com',
            phone='63999990000',
            whatsapp_number='5563999990000',
            min_order_value=Decimal('0.00'),
            default_delivery_fee=Decimal('0.00'),
        )
        defaults.update(kwargs)
        return Store.objects.create(**defaults)

    def _setup_catalog(self, store):
        category = StoreCategory.objects.create(
            store=store, name='Cat', slug=f'cat-{store.slug}', is_active=True, sort_order=1
        )
        product = StoreProduct.objects.create(
            store=store,
            category=category,
            name='Produto',
            slug=f'produto-{store.slug}',
            price=Decimal('10.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
            stock_quantity=99,
        )
        return product

    def _cart_key(self, store):
        return f'cart-key-{store.slug}'

    def _create_cart_with_item(self, store, product):
        cart = StoreCart.objects.create(store=store, session_key=self._cart_key(store))
        StoreCartItem.objects.create(cart=cart, product=product, quantity=1)
        return cart

    def _checkout_payload(self):
        return {
            'customer_name': 'Cliente Teste',
            'customer_email': 'cli@example.com',
            'customer_phone': '+5563999990001',
            'delivery_method': 'pickup',
            'payment_method': '',
        }

    def _create_orders(self, store, count):
        for i in range(count):
            StoreOrder.objects.create(
                store=store,
                order_number=f'{store.slug}-{i:04d}',
                customer_name='Cliente Histórico',
                customer_phone='63999990002',
                subtotal=Decimal('10.00'),
                total=Decimal('10.00'),
            )

    def test_checkout_bloqueado_quando_excede_limite_free(self):
        store = self._store('loja-free-limit', plan='free')
        product = self._setup_catalog(store)
        self._create_orders(store, 30)
        self._create_cart_with_item(store, product)

        response = self.client.post(
            f'/api/v1/stores/{store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(store),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('limite do plano', response.json().get('detail', '').lower())

    def test_checkout_nao_bloqueado_quando_plano_pago_excede_30(self):
        store = self._store('loja-pro-limit', plan='pro')
        product = self._setup_catalog(store)
        self._create_orders(store, 35)
        self._create_cart_with_item(store, product)

        response = self.client.post(
            f'/api/v1/stores/{store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(store),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_checkout_nao_bloqueado_quando_free_isento_excede_30(self):
        store = self._store('loja-free-isenta', plan='free', billing_exempt=True)
        product = self._setup_catalog(store)
        self._create_orders(store, 35)
        self._create_cart_with_item(store, product)

        response = self.client.post(
            f'/api/v1/stores/{store.slug}/checkout/',
            self._checkout_payload(),
            format='json',
            HTTP_X_CART_KEY=self._cart_key(store),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
