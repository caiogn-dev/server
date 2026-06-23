"""Checkout que muda estoque de produto invalida o cardápio cacheado do agente.

O decremento de estoque a nível de produto usa
`StoreProduct.objects.filter(...).update(stock_quantity=F(...)-qty)`, que NÃO
dispara `post_save`. Por isso `CheckoutService.create_order` agenda, via
`transaction.on_commit`, a invalidação da chave de cache do cardápio do agente
(`agent:menu_ctx:<store_id>`). Sem `captureOnCommitCallbacks(execute=True)` o
callback de on_commit NÃO roda dentro da transação de teste do `TestCase`.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.agents.services.langchain_service import menu_context_cache_key
from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreCategory,
    StoreProduct,
)
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CheckoutMenuInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username='menu-inval-owner',
            email='menu-inval-owner@example.com',
            password='unused-test-password',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Loja Estoque',
            slug='loja-estoque-menu',
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

    def _customer_data(self):
        return {
            'name': 'Cliente Estoque',
            'email': 'cliente@example.com',
            'phone': '+5563999990099',
        }

    def test_product_track_stock_checkout_invalidates_agent_menu_cache(self):
        product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Salada Tracked',
            slug='salada-tracked',
            price=Decimal('29.90'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=True,
            stock_quantity=5,
        )
        cart = StoreCart.objects.create(store=self.store, session_key='menu-inval-cart')
        StoreCartItem.objects.create(cart=cart, product=product, quantity=2)

        # Pré-popula o cardápio cacheado do agente.
        key = menu_context_cache_key(self.store.id)
        cache.set(key, 'CARDÁPIO FAKE', 1800)
        self.assertIsNotNone(cache.get(key))

        # on_commit só roda se capturado/executado.
        with self.captureOnCommitCallbacks(execute=True):
            order = CheckoutService.create_order(
                cart=cart,
                customer_data=self._customer_data(),
                delivery_data={'method': 'pickup'},
            )

        # A venda decrementou estoque a nível de produto → cache invalidado.
        self.assertIsNone(cache.get(key))

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 3)
        self.assertEqual(order.store_id, self.store.id)

    def test_non_track_stock_checkout_still_succeeds(self):
        product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Salada Untracked',
            slug='salada-untracked',
            price=Decimal('19.90'),
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
            stock_quantity=10,
        )
        cart = StoreCart.objects.create(store=self.store, session_key='menu-inval-cart-2')
        StoreCartItem.objects.create(cart=cart, product=product, quantity=1)

        with self.captureOnCommitCallbacks(execute=True):
            order = CheckoutService.create_order(
                cart=cart,
                customer_data=self._customer_data(),
                delivery_data={'method': 'pickup'},
            )

        self.assertEqual(order.store_id, self.store.id)
        self.assertEqual(order.items.count(), 1)
