"""Recálculo de fidelidade de pedido já creditado (12/ago).

Caso real (Aline Nasche, CE-2608113992): o "Combo Queridinha" foi vendido
valendo 1 selo; a dona ajustou `loyalty_units` pra 8 DEPOIS da entrega. Como
`credit_order` é uma fotografia idempotente por `unique(order, kind='earn')`,
o pedido dela ficou congelado em 1 e não havia caminho no painel pra corrigir.

`recalculate_order_credit` reabre a transação EARN existente, recalcula pelas
regras de hoje e ajusta o saldo da conta pela diferença — pra mais ou pra
menos — sem nunca duplicar o crédito nem deixar o saldo negativo.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import (
    Store,
    StoreLoyaltyAccount,
    StoreLoyaltyTransaction,
    StoreOrder,
    StoreOrderItem,
    StoreProduct,
    StoreCategory,
)
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


class LoyaltyRecalculoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono-rec', password='x')
        self.store = Store.objects.create(
            name='Loja REC', slug='loja-rec', owner=owner, status='active',
        )
        self.categoria = StoreCategory.objects.create(
            store=self.store, name='Saladas', slug='saladas',
        )
        self.store.metadata = {
            'loyalty_qualifying_categories': [str(self.categoria.id)],
        }
        self.store.save(update_fields=['metadata'])
        self.customer = User.objects.create_user(username='cliente-rec', password='x')

    def _pedido_com_produto(self, produto, quantity=1):
        order = StoreOrder.objects.create(
            store=self.store, customer=self.customer, subtotal=50, total=50,
        )
        StoreOrderItem.objects.create(
            order=order, product=produto, product_name=produto.name,
            unit_price=50, quantity=quantity, subtotal=50,
        )
        return order

    def _produto(self, name='Combo Queridinha', attributes=None):
        return StoreProduct.objects.create(
            store=self.store, category=self.categoria, name=name,
            slug=name.lower().replace(' ', '-'), price=50,
            attributes=attributes or {},
        )

    def _saldo(self):
        conta = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        return conta.qualified_count

    def test_recalculo_corrige_pedido_creditado_a_menos(self):
        """O caso da Aline: creditou 1, produto virou 8 selos, recálculo ajusta."""
        produto = self._produto()
        order = self._pedido_com_produto(produto)
        self.assertEqual(LoyaltyService.credit_order(order).quantity, 1)
        self.assertEqual(self._saldo(), 1)

        produto.attributes = {'loyalty_units': 8}
        produto.save(update_fields=['attributes'])

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['before'], 1)
        self.assertEqual(resultado['after'], 8)
        self.assertEqual(resultado['delta'], 7)
        self.assertEqual(self._saldo(), 8)
        # Uma única transação EARN — nunca duplica o crédito.
        self.assertEqual(
            StoreLoyaltyTransaction.objects.filter(order=order, kind='earn').count(), 1,
        )

    def test_recalculo_corrige_pedido_creditado_a_mais(self):
        produto = self._produto(attributes={'loyalty_units': 8})
        order = self._pedido_com_produto(produto)
        LoyaltyService.credit_order(order)
        self.assertEqual(self._saldo(), 8)

        produto.attributes = {'loyalty_units': 2}
        produto.save(update_fields=['attributes'])

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['delta'], -6)
        self.assertEqual(self._saldo(), 2)

    def test_recalculo_nao_deixa_saldo_negativo(self):
        """Resgate já consumiu o saldo: a conta trava no zero, não vira negativa."""
        produto = self._produto(attributes={'loyalty_units': 8})
        order = self._pedido_com_produto(produto)
        LoyaltyService.credit_order(order)
        conta = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        conta.qualified_count = 3  # saldo já mexido por fora
        conta.save(update_fields=['qualified_count'])

        produto.attributes = {}
        produto.save(update_fields=['attributes'])
        LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(self._saldo(), 0)

    def test_recalculo_sem_mudanca_e_noop(self):
        produto = self._produto(attributes={'loyalty_units': 4})
        order = self._pedido_com_produto(produto)
        LoyaltyService.credit_order(order)

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['delta'], 0)
        self.assertEqual(resultado['changed'], False)
        self.assertEqual(self._saldo(), 4)

    def test_recalculo_credita_pedido_que_nunca_foi_creditado(self):
        """Pedido entregue antes do produto ganhar selos: cria o crédito."""
        produto = self._produto(attributes={'loyalty_units': 5})
        order = self._pedido_com_produto(produto)
        self.assertFalse(StoreLoyaltyTransaction.objects.filter(order=order).exists())

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['before'], 0)
        self.assertEqual(resultado['after'], 5)
        self.assertEqual(self._saldo(), 5)

    def test_recalculo_de_pedido_sem_cliente_nao_quebra(self):
        produto = self._produto(attributes={'loyalty_units': 5})
        order = StoreOrder.objects.create(store=self.store, subtotal=50, total=50)
        StoreOrderItem.objects.create(
            order=order, product=produto, product_name=produto.name,
            unit_price=50, quantity=1, subtotal=50,
        )

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['changed'], False)
        self.assertEqual(resultado['reason'], 'sem_cliente')

    def test_recalculo_zera_credito_quando_produto_perde_os_selos(self):
        produto = self._produto(attributes={'loyalty_units': 6})
        order = self._pedido_com_produto(produto)
        LoyaltyService.credit_order(order)
        # Produto sai da categoria qualificante e perde os selos
        outra = StoreCategory.objects.create(
            store=self.store, name='Bebidas', slug='bebidas',
        )
        produto.category = outra
        produto.attributes = {}
        produto.save(update_fields=['category', 'attributes'])

        resultado = LoyaltyService.recalculate_order_credit(order)

        self.assertEqual(resultado['after'], 0)
        self.assertEqual(self._saldo(), 0)
        self.assertEqual(
            StoreLoyaltyTransaction.objects.filter(order=order, kind='earn').count(), 0,
        )
