"""Mudar a quantidade na sacola nunca pode virar erro 500.

O CASO REAL (05/10, Cê Saladas): `PATCH /cart/item/<id>/` respondeu 500 para
"Estoque insuficiente. Disponível: 1" — a view não capturava o `ValueError`
de regra de negócio que o `add` já devolve como 400. O cliente via um erro
genérico em vez de "só tem 1".

E o "+" de COMBO: o `CartContext` da vitrine manda o id do
`StoreCartComboItem` para o mesmo endpoint, mas a view só procurava
`StoreCartItem` → "Item not found" → 500. Combo na sacola não aumentava.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreProduct
from apps.stores.models.cart import StoreCartComboItem
from apps.stores.tests.factories import make_combo_with_groups

User = get_user_model()


class AlterarQuantidadeNaSacolaTest(APITestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-qtd', email='q@t.com', password='x')
        self.loja = Store.objects.create(
            owner=dono, name='Loja Qtd', slug='loja-qtd', status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD,
        )
        cat = StoreCategory.objects.create(store=self.loja, name='Cat', slug='cat-qtd', is_active=True)
        self.salada = StoreProduct.objects.create(
            store=self.loja, category=cat, name='Salada', slug='salada-qtd',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=True, stock_quantity=1, allow_backorder=False,
        )
        self.sacola = StoreCart.objects.create(store=self.loja, session_key='sess-qtd')

    def _patch(self, item_id, quantidade):
        return self.client.patch(
            f'/api/v1/stores/{self.loja.slug}/cart/item/{item_id}/',
            {'quantity': quantidade}, format='json', HTTP_X_CART_KEY=self.sacola.session_key,
        )

    def test_estoque_insuficiente_responde_400_com_a_mensagem(self):
        item = StoreCartItem.objects.create(cart=self.sacola, product=self.salada, quantity=1)
        resp = self._patch(item.id, 2)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('Disponível: 1', resp.json()['error'])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_mais_de_combo_aumenta_a_quantidade(self):
        _, combo = make_combo_with_groups(groups=1, variants=1, options=0, store=self.loja)
        item = StoreCartComboItem.objects.create(cart=self.sacola, combo=combo, quantity=1)
        resp = self._patch(item.id, 3)
        self.assertEqual(resp.status_code, 200, resp.content)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)
        self.assertEqual(resp.json()['combo_items'][0]['quantity'], 3)

    def test_zero_remove_o_combo(self):
        _, combo = make_combo_with_groups(groups=1, variants=1, options=0, store=self.loja)
        item = StoreCartComboItem.objects.create(cart=self.sacola, combo=combo, quantity=2)
        resp = self._patch(item.id, 0)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(StoreCartComboItem.objects.filter(id=item.id).exists())

    def test_item_de_outra_sacola_responde_404(self):
        outra = StoreCart.objects.create(store=self.loja, session_key='sess-outra')
        alheio = StoreCartItem.objects.create(cart=outra, product=self.salada, quantity=1)
        resp = self._patch(alheio.id, 1)
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_quantidade_que_nao_e_numero_responde_400(self):
        item = StoreCartItem.objects.create(cart=self.sacola, product=self.salada, quantity=1)
        resp = self._patch(item.id, 'abc')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_id_que_nao_e_uuid_responde_404(self):
        resp = self._patch('temp_salad_123', 1)
        self.assertEqual(resp.status_code, 404, resp.content)
