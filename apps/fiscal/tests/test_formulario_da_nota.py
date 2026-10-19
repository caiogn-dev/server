"""O formulário de emissão mexe no PEDIDO: nota e pedido nunca divergem.

19/10/2026, Ivoneth: coffee break de 50 pessoas virou 60, com entrega. Não
havia como pôr na nota "+10 pessoas" — o formulário só escolhia pedido e
destinatário. O acréscimo foi lançado solto e a nota foi recusada.

Agora a etapa Produtos do formulário lê os itens e valores do pedido e grava
de volta pelo /adjust/: item do cardápio, item fora do cardápio e preço.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()


class FormularioDaNotaTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-form-nota', password='x')
        self.store = Store.objects.create(
            name='Loja Form Nota', slug='loja-form-nota', owner=self.owner, status='active',
        )
        categoria = StoreCategory.objects.create(store=self.store, name='Coffee', slug='coffee')
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Coffee Break 50 Pessoas', price=Decimal('1695.00'),
            track_stock=False, category=categoria,
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Sindicato', customer_phone='5563992243412',
            subtotal=Decimal('1695.00'), total=Decimal('1745.00'),
            delivery_fee=Decimal('50.00'), payment_method='pix', status='confirmed',
        )
        self.item = StoreOrderItem.objects.create(
            order=self.order, product=self.produto, product_name=self.produto.name,
            unit_price=Decimal('1695.00'), quantity=1, subtotal=Decimal('1695.00'),
        )
        self.client.force_authenticate(self.owner)
        self.ajuste = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/adjust/'

    def test_item_fora_do_cardapio_entra_no_pedido(self):
        resp = self.client.post(self.ajuste, {'item_ops': [
            {'op': 'add_custom', 'name': 'Adicional 10 pessoas', 'quantity': 1, 'unit_price': '299.00'},
        ]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        avulso = self.order.items.get(product__isnull=True)
        self.assertEqual(avulso.product_name, 'Adicional 10 pessoas')
        self.assertEqual(avulso.subtotal, Decimal('299.00'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, Decimal('2044.00'))

    def test_item_fora_do_cardapio_exige_nome_e_preco(self):
        resp = self.client.post(self.ajuste, {'item_ops': [
            {'op': 'add_custom', 'name': ' ', 'quantity': 1, 'unit_price': '10.00'},
        ]}, format='json')
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(self.ajuste, {'item_ops': [
            {'op': 'add_custom', 'name': 'Sem preço', 'quantity': 1},
        ]}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_muda_preco_e_nome_do_item(self):
        resp = self.client.post(self.ajuste, {'item_ops': [
            {'op': 'update', 'item_id': str(self.item.id), 'quantity': 1,
             'unit_price': '1994.00', 'name': 'Coffee Break 60 Pessoas'},
        ]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        self.item.refresh_from_db()
        self.assertEqual(self.item.unit_price, Decimal('1994.00'))
        self.assertEqual(self.item.subtotal, Decimal('1994.00'))
        self.assertEqual(self.item.product_name, 'Coffee Break 60 Pessoas')
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, Decimal('2044.00'))

    def test_pedido_para_nota_traz_itens_e_valores(self):
        self.order.surcharge_value = Decimal('10.00')
        self.order.discount = Decimal('5.00')
        self.order.save()
        self.order.recalculate_totals()

        resp = self.client.get(
            f'/api/v1/stores/{self.store.slug}/fiscal/pedidos/', {'id': str(self.order.id)},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        pedido = resp.data[0]

        self.assertEqual(pedido['itens'], [{
            'id': str(self.item.id), 'nome': 'Coffee Break 50 Pessoas', 'quantidade': 1,
            'valor_unitario': '1695.00', 'subtotal': '1695.00', 'do_cardapio': True,
        }])
        self.assertEqual(pedido['valores'], {
            'itens': '1695.00', 'frete': '50.00', 'desconto': '5.00',
            'acrescimo': '10.00', 'taxa_do_vale': '0.00', 'total': '1750.00',
        })
        self.assertEqual(pedido['payment_method'], 'pix')
