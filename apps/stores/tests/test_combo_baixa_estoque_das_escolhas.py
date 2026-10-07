"""Combo baixa o estoque dos pratos ESCOLHIDOS dentro dele.

Dono 07/10 (Agrião): "o estoque é importante pois precisamos dele para
contabilização e para saber quando acabar o produto e não vender sem estoque".
Até aqui a venda de um combo só mexia no estoque do próprio combo: o Combo
Família com 30 marmitas saía e o estoque de cada marmita ficava parado, e o
cliente conseguia escolher um sabor esgotado.

Regra: cada escolha baixa (quantidade escolhida × quantidade de combos) do
produto — ou da variante — quando o produto controla estoque. Cancelar devolve
o mesmo, mas só para pedido criado com esta regra (marca no display_data):
pedido antigo nunca baixou, e devolver inflaria o estoque.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.stores.models import (
    Store, StoreCart, StoreCartComboItem, StoreCombo, StoreOrderComboItem, StoreProduct,
    StoreProductVariant,
)
from apps.stores.models.combo_group import ComboProductGroup
from apps.stores.services.cart_service import CartService
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ComboBaixaEstoqueDasEscolhasTests(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dono-combo-estoque', password='x')
        self.loja = Store.objects.create(
            owner=dono, name='Agrião', slug='agriao-teste', status=Store.StoreStatus.ACTIVE,
            min_order_value=Decimal('0'), latitude=Decimal('-10.18'), longitude=Decimal('-48.33'),
        )
        self.picadinho = StoreProduct.objects.create(
            store=self.loja, name='Picadinho', slug='picadinho', price=Decimal('20'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=True, stock_quantity=10,
        )
        self.assadinho = StoreProduct.objects.create(
            store=self.loja, name='Assadinho', slug='assadinho', price=Decimal('20'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=True, stock_quantity=10,
        )
        self.sem_controle = StoreProduct.objects.create(
            store=self.loja, name='Caldo', slug='caldo', price=Decimal('15'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=False, stock_quantity=0,
        )
        self.combo = StoreCombo.objects.create(
            store=self.loja, name='Combo 3', slug='combo-3', price=Decimal('50'),
        )
        self.grupo = ComboProductGroup.objects.create(
            combo=self.combo, title='Escolha 3 pratos', min_selections=3, max_selections=3,
            allow_duplicate_variants=True,
        )

    def _selecoes(self, *produtos):
        return {str(self.grupo.id): [str(p.id) for p in produtos]}

    def _comprar(self, selecoes, quantidade=1):
        cart = StoreCart.objects.create(store=self.loja, session_key=f'c-{StoreCart.objects.count()}')
        StoreCartComboItem.objects.create(
            cart=cart, combo=self.combo, quantity=quantidade, group_selections=selecoes,
            customizations={'selections': selecoes},
        )
        with self.captureOnCommitCallbacks(execute=True):
            return CheckoutService.create_order(
                cart=cart,
                customer_data={'name': 'Ana', 'email': 'ana@example.com', 'phone': '+5563999990001'},
                delivery_data={'method': 'pickup'},
            )

    def _estoque(self, produto):
        produto.refresh_from_db()
        return produto.stock_quantity

    def test_venda_baixa_cada_escolha_vezes_a_quantidade_de_combos(self):
        self._comprar(self._selecoes(self.picadinho, self.assadinho, self.assadinho), quantidade=2)

        self.assertEqual(self._estoque(self.picadinho), 8)   # 1 × 2
        self.assertEqual(self._estoque(self.assadinho), 6)   # 2 × 2
        self.picadinho.refresh_from_db()
        self.assertEqual(self.picadinho.sold_count, 2)

    def test_produto_sem_controle_nao_mexe(self):
        self._comprar(self._selecoes(self.sem_controle, self.picadinho, self.picadinho))
        self.assertEqual(self._estoque(self.sem_controle), 0)
        self.assertEqual(self._estoque(self.picadinho), 8)

    def test_variante_escolhida_baixa_a_variante(self):
        suco = StoreProduct.objects.create(
            store=self.loja, name='Suco', slug='suco', price=Decimal('8'),
            status=StoreProduct.ProductStatus.ACTIVE, track_stock=True, stock_quantity=0,
        )
        v500 = StoreProductVariant.objects.create(product=suco, name='500ml', stock_quantity=5)
        self._comprar({str(self.grupo.id): [str(v500.id), str(v500.id), str(self.picadinho.id)]})
        v500.refresh_from_db()
        self.assertEqual(v500.stock_quantity, 3)

    def test_cancelar_devolve_as_escolhas(self):
        pedido = self._comprar(self._selecoes(self.picadinho, self.assadinho, self.assadinho))
        CheckoutService._restore_stock(pedido)
        self.assertEqual(self._estoque(self.picadinho), 10)
        self.assertEqual(self._estoque(self.assadinho), 10)

    def test_reativar_pedido_baixa_de_novo(self):
        pedido = self._comprar(self._selecoes(self.picadinho, self.assadinho, self.assadinho))
        CheckoutService._restore_stock(pedido)
        CheckoutService._baixar_estoque_de_novo(pedido)
        self.assertEqual(self._estoque(self.assadinho), 8)

    def test_pedido_antigo_sem_marca_nao_devolve(self):
        pedido = self._comprar(self._selecoes(self.picadinho, self.assadinho, self.assadinho))
        # Simula pedido de antes da regra: as escolhas existem, a marca não.
        ci = StoreOrderComboItem.objects.get(order=pedido)
        ci.display_data = {k: v for k, v in ci.display_data.items() if k != 'estoque_das_escolhas'}
        ci.save(update_fields=['display_data'])
        CheckoutService._restore_stock(pedido)
        self.assertEqual(self._estoque(self.assadinho), 8)

    def test_carrinho_recusa_sabor_esgotado(self):
        self.assadinho.stock_quantity = 1
        self.assadinho.save(update_fields=['stock_quantity'])
        cart = StoreCart.objects.create(store=self.loja, session_key='esgotado')
        with self.assertRaisesMessage(ValueError, 'Assadinho'):
            CartService.add_combo(
                cart, self.combo, quantity=1,
                group_selections=self._selecoes(self.picadinho, self.assadinho, self.assadinho),
            )

    def test_carrinho_soma_a_quantidade_de_combos(self):
        self.assadinho.stock_quantity = 3
        self.assadinho.save(update_fields=['stock_quantity'])
        cart = StoreCart.objects.create(store=self.loja, session_key='dois-combos')
        with self.assertRaises(ValueError):
            CartService.add_combo(
                cart, self.combo, quantity=2,   # 2 × 2 assadinhos = 4 > 3
                group_selections=self._selecoes(self.picadinho, self.assadinho, self.assadinho),
            )

    def test_carrinho_aceita_com_estoque_e_ignora_sem_controle(self):
        cart = StoreCart.objects.create(store=self.loja, session_key='ok')
        CartService.add_combo(
            cart, self.combo, quantity=1,
            group_selections=self._selecoes(self.sem_controle, self.assadinho, self.assadinho),
        )
        self.assertEqual(cart.combo_items.count(), 1)

    def test_aceita_encomenda_nao_barra(self):
        self.assadinho.stock_quantity = 0
        self.assadinho.allow_backorder = True
        self.assadinho.save(update_fields=['stock_quantity', 'allow_backorder'])
        cart = StoreCart.objects.create(store=self.loja, session_key='encomenda')
        CartService.add_combo(
            cart, self.combo, quantity=1,
            group_selections=self._selecoes(self.picadinho, self.assadinho, self.assadinho),
        )
        self.assertEqual(cart.combo_items.count(), 1)
