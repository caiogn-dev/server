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
