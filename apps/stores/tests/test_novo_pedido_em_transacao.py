"""Regressão 28/10: pedido do painel deu 500 em produção.

O `@transaction.atomic` do `create` foi parar em outro método e o
`select_for_update` do estoque rodou fora de transação. O APITestCase comum
embrulha o teste numa transação e escondia o erro — aqui não.
"""
from decimal import Decimal

from rest_framework.test import APIClient
from django.test import TransactionTestCase

from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_product, make_store


class PedidoDoPainelForaDeTransacaoTests(TransactionTestCase):
    def test_pedido_com_estoque_controlado_nao_quebra(self):
        loja = make_store()
        prato = make_product(loja, name='Prato', price=Decimal('30.00'))
        prato.track_stock = True
        prato.stock_quantity = 5
        prato.save(update_fields=['track_stock', 'stock_quantity'])
        cliente = APIClient()
        cliente.force_authenticate(loja.owner)
        r = cliente.post(f'/api/v1/stores/{loja.slug}/orders/', {
            'store': str(loja.id), 'customer_name': 'Ana', 'customer_phone': '5563999990003',
            'delivery_method': 'pickup', 'payment_method': 'cash', 'source': 'dashboard',
            'items': [{'product_id': str(prato.id), 'quantity': 1}],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(StoreOrder.objects.count(), 1)
