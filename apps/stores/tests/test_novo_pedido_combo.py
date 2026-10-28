"""Combo no novo pedido do painel (28/10).

O painel só carregava produtos e o POST de pedido só aceitava `product_id`:
combo não tinha como entrar num pedido de balcão. Agora o item pode ser
`combo_id` + `selections`, validado, cobrado e baixado igual ao checkout.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.stores.models import StoreOrder, StoreOrderComboItem, StoreProduct
from apps.stores.models.combo_group import ComboProductGroup, ComboProductGroupProductOption
from apps.stores.tests.factories import make_combo_with_groups, make_product, make_store


class NovoPedidoComboTests(APITestCase):
    def setUp(self):
        self.store, self.combo = make_combo_with_groups(groups=1, variants=0, options=2)
        self.grupo = ComboProductGroup.objects.get(combo=self.combo)
        ComboProductGroup.objects.filter(id=self.grupo.id).update(max_selections=1)
        self.sabor = ComboProductGroupProductOption.objects.filter(group=self.grupo).first().product
        self.client.force_authenticate(self.store.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def criar(self, itens):
        return self.client.post(self.url, {
            'store': str(self.store.id), 'customer_name': 'Ana', 'customer_phone': '5563999990002',
            'delivery_method': 'pickup', 'payment_method': 'cash', 'source': 'dashboard',
            'items': itens,
        }, format='json')

    def item_do_combo(self, **extra):
        item = {'combo_id': str(self.combo.id), 'quantity': 2,
                'selections': {str(self.grupo.id): [str(self.sabor.id)]}}
        item.update(extra)
        return item

    def test_combo_entra_no_pedido_com_preco_e_escolhas(self):
        r = self.criar([self.item_do_combo()])
        self.assertEqual(r.status_code, 201, r.content)
        pedido = StoreOrder.objects.get(id=r.data['id'])
        linha = pedido.items.get()
        self.assertEqual(linha.product_name, f'Combo: {self.combo.name}')
        self.assertEqual(linha.unit_price, Decimal('50.00'))
        self.assertEqual(linha.quantity, 2)
        self.assertEqual(pedido.total, Decimal('100.00'))
        escolha = StoreOrderComboItem.objects.get(order=pedido)
        self.assertEqual(escolha.order_item, linha)
        self.assertEqual(escolha.quantity, 2)
        self.assertIn(str(self.sabor.id), str(escolha.group_selections))

    def test_combo_e_produto_no_mesmo_pedido(self):
        prato = make_product(self.store, name='Prato avulso', price=Decimal('20.00'))
        r = self.criar([self.item_do_combo(quantity=1), {'product_id': str(prato.id), 'quantity': 1}])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(StoreOrder.objects.get(id=r.data['id']).total, Decimal('70.00'))

    def test_escolha_obrigatoria_faltando_recusa(self):
        r = self.criar([self.item_do_combo(selections={})])
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(StoreOrder.objects.exists())

    def test_combo_de_outra_loja_recusa(self):
        _, alheio = make_combo_with_groups(groups=1, variants=0, options=1, store=make_store())
        r = self.criar([{'combo_id': str(alheio.id), 'quantity': 1, 'selections': {}}])
        self.assertEqual(r.status_code, 400, r.content)

    def test_item_sem_produto_nem_combo_recusa(self):
        r = self.criar([{'quantity': 1}])
        self.assertEqual(r.status_code, 400, r.content)

    def test_sabor_escolhido_sai_do_estoque(self):
        StoreProduct.objects.filter(id=self.sabor.id).update(track_stock=True, stock_quantity=10)
        r = self.criar([self.item_do_combo()])
        self.assertEqual(r.status_code, 201, r.content)
        self.sabor.refresh_from_db()
        self.assertEqual(self.sabor.stock_quantity, 8)

    def test_sabor_esgotado_recusa(self):
        StoreProduct.objects.filter(id=self.sabor.id).update(track_stock=True, stock_quantity=1, allow_backorder=False)
        r = self.criar([self.item_do_combo()])
        self.assertEqual(r.status_code, 400, r.content)
        corpo = r.content.decode().lower()
        self.assertTrue('esgotado' in corpo or 'restam' in corpo, corpo)
