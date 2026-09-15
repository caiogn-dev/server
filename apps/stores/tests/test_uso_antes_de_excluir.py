"""O painel pergunta "onde isto aparece?" antes de excluir produto ou categoria.

O dono não tinha como remover produto/categoria (15/set). Excluir é seguro para
o histórico (item do pedido guarda o nome), mas tira o produto de todo combo
em silêncio — então a tela avisa com números antes.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()


class TestUsoAntesDeExcluir(APITestCase):

    def setUp(self):
        self.dono = User.objects.create_user(username='dono_uso', password='x')
        self.loja = Store.objects.create(owner=self.dono, name='Loja Uso', slug='loja-uso', status='active')
        self.categoria = StoreCategory.objects.create(store=self.loja, name='Saladas', slug='saladas')
        self.produto = StoreProduct.objects.create(store=self.loja, name='Caesar', slug='caesar',
                                                   price=Decimal('30'), category=self.categoria)
        pedido = StoreOrder.objects.create(store=self.loja, total=Decimal('30'), subtotal=Decimal('30'))
        StoreOrderItem.objects.create(order=pedido, product=self.produto, product_name='Caesar',
                                      unit_price=Decimal('30'), quantity=1, subtotal=Decimal('30'))
        self.client.force_authenticate(self.dono)

    def test_uso_do_produto(self):
        resp = self.client.get(f'/api/v1/stores/products/{self.produto.id}/uso/')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {'combos': 0, 'pedidos': 1})

    def test_excluir_produto_mantem_o_pedido(self):
        resp = self.client.delete(f'/api/v1/stores/products/{self.produto.id}/')

        self.assertIn(resp.status_code, (200, 204), resp.content)
        item = StoreOrderItem.objects.get()
        self.assertIsNone(item.product_id)
        self.assertEqual(item.product_name, 'Caesar')

    def test_uso_da_categoria(self):
        resp = self.client.get(f'/api/v1/stores/categories/{self.categoria.id}/uso/')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {'produtos': 1})

    def test_excluir_categoria_deixa_produto_sem_categoria(self):
        resp = self.client.delete(f'/api/v1/stores/categories/{self.categoria.id}/')

        self.assertIn(resp.status_code, (200, 204), resp.content)
        self.produto.refresh_from_db()
        self.assertIsNone(self.produto.category_id)
