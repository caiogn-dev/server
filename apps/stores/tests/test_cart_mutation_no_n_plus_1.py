"""Guarda de regressão de performance no storefront público (endpoint de alto
tráfego, ce-saladas): a serialização do carrinho em mutações (add/update/
remove/clear) deve ser O(1) em relação ao número de ITENS SIMPLES — sem N+1
por produto/variante.

NOTA: medição (03/jul) mostrou que itens simples já são O(1) (+1 query para 3
itens extras) — a suspeita de N+1 de produto estava superestimada. O custo real
que ESCALA está nos COMBOS, dentro de `CheckoutService.build_combo_selection_
snapshot`, que emite queries próprias por combo e ignora prefetch do carrinho;
isso exige batching no snapshot (refactor à parte, não coberto aqui). Este teste
trava a garantia O(1) dos itens simples para não regredir.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreProduct
from apps.stores.models.cart import StoreCartComboItem
from apps.stores.tests.factories import make_combo_with_groups

User = get_user_model()


class CartMutationNoNPlus1Test(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='cart-owner', email='c@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Loja Cart', slug='loja-cart', status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-cart', is_active=True, sort_order=1,
        )
        self.products = [
            StoreProduct.objects.create(
                store=self.store, category=self.category, name=f'P{i}', slug=f'p{i}-cart',
                price=Decimal('10.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
            )
            for i in range(5)
        ]

    def _make_cart(self, session, n_items):
        cart = StoreCart.objects.create(store=self.store, session_key=session)
        for i in range(n_items):
            StoreCartItem.objects.create(cart=cart, product=self.products[i], quantity=1)
        return cart

    def _patch_first_item(self, cart):
        item = cart.items.first()
        url = f'/api/v1/stores/{self.store.slug}/cart/item/{item.id}/'
        return self.client.patch(url, {'quantity': 1}, format='json', HTTP_X_CART_KEY=cart.session_key)

    def test_serializacao_do_carrinho_nao_escala_com_n_itens(self):
        small = self._make_cart('sess-small', 1)
        large = self._make_cart('sess-large', 4)

        with CaptureQueriesContext(connection) as q_small:
            resp_s = self._patch_first_item(small)
        self.assertEqual(resp_s.status_code, 200, resp_s.content)

        with CaptureQueriesContext(connection) as q_large:
            resp_l = self._patch_first_item(large)
        self.assertEqual(resp_l.status_code, 200, resp_l.content)

        delta = len(q_large) - len(q_small)
        # 3 itens extras no carrinho grande. Com N+1 (product+variant por item)
        # o delta seria ~6; com prefetch deve ficar em ~0 (folga de 2).
        self.assertLessEqual(
            delta, 2,
            f'N+1 na serialização do carrinho: +{delta} queries para 3 itens extras '
            f'(pequeno={len(q_small)}, grande={len(q_large)})',
        )


class CartComboMutationNoNPlus1Test(APITestCase):
    """O custo que ESCALA de verdade (medição 03/jul): cada COMBO no carrinho
    dispara queries próprias em `get_selected_variants_data` (groups +
    variant_limits + variants + products) e mais o FK `combo` sem prefetch —
    ~5 queries por combo em TODA mutação e GET do carrinho. A serialização
    deve ser O(1) em relação ao número de combos (resolução em lote)."""

    def setUp(self):
        self.owner = User.objects.create_user(username='combo-cart-owner', email='cc@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Loja Combo Cart', slug='loja-combo-cart',
            status=Store.StoreStatus.ACTIVE, store_type=Store.StoreType.FOOD,
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-combo-cart', is_active=True, sort_order=1,
        )
        self.simple_product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Simples', slug='p-simples-combo-cart',
            price=Decimal('10.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        # 3 combos reais com 2 grupos x 2 variantes cada, no MESMO tenant
        self.combos = [
            make_combo_with_groups(groups=2, variants=2, options=0, store=self.store)[1]
            for _ in range(3)
        ]

    def _selections_for(self, combo):
        return {
            str(group.id): [str(limit.variant_id) for limit in group.variant_limits.all()[:1]]
            for group in combo.groups.all()
        }

    def _make_cart(self, session, n_combos):
        cart = StoreCart.objects.create(store=self.store, session_key=session)
        StoreCartItem.objects.create(cart=cart, product=self.simple_product, quantity=1)
        for combo in self.combos[:n_combos]:
            StoreCartComboItem.objects.create(
                cart=cart, combo=combo, quantity=1,
                group_selections=self._selections_for(combo),
            )
        return cart

    def _patch_first_item(self, cart):
        item = cart.items.first()
        url = f'/api/v1/stores/{self.store.slug}/cart/item/{item.id}/'
        return self.client.patch(url, {'quantity': 1}, format='json', HTTP_X_CART_KEY=cart.session_key)

    def test_serializacao_do_carrinho_nao_escala_com_n_combos(self):
        small = self._make_cart('sess-combo-small', 1)
        large = self._make_cart('sess-combo-large', 3)

        with CaptureQueriesContext(connection) as q_small:
            resp_s = self._patch_first_item(small)
        self.assertEqual(resp_s.status_code, 200, resp_s.content)

        with CaptureQueriesContext(connection) as q_large:
            resp_l = self._patch_first_item(large)
        self.assertEqual(resp_l.status_code, 200, resp_l.content)

        # Sanidade: o snapshot precisa vir resolvido (não vazio) nos dois casos
        for resp in (resp_s, resp_l):
            for combo_item in resp.json()['combo_items']:
                self.assertTrue(combo_item['selected_variants_data'],
                                'selected_variants_data vazio — teste não exercita o snapshot')

        delta = len(q_large) - len(q_small)
        # 2 combos extras no carrinho grande. Com o custo atual (~5 queries por
        # combo) o delta é ~10; com resolução em lote deve ficar ~0 (folga de 3).
        self.assertLessEqual(
            delta, 3,
            f'N+1 de combos na serialização do carrinho: +{delta} queries para 2 combos extras '
            f'(pequeno={len(q_small)}, grande={len(q_large)})',
        )
