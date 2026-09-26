"""Pedido reembolsado: fora do faturamento E contado junto do cancelado.

Dono (26/09): "pedidos cancelados e reembolsados não entram como receita" e
"coloque no painel Reembolsado". O dinheiro já ficava de fora (payment_status
≠ paid), mas o resumo da lista dizia `cancelados: 0` com um reembolsado na
tela — parecia que o reembolso não tinha sido descontado.
"""
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.models import User
from apps.stores import metrics
from apps.stores.models import Store, StoreOrder


class ResumoReembolsadoTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dono-reemb', password='x', email='r@real.com')
        self.store = Store.objects.create(name='Loja R', slug='loja-r', owner=owner, status='active')

    def _pedido(self, total, *, status='delivered', payment_status='paid'):
        p = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5563900000000',
            customer_email='c@real.com', subtotal=Decimal(total), total=Decimal(total),
            status=status, payment_status=payment_status,
        )
        agora = timezone.now()
        StoreOrder.objects.filter(pk=p.pk).update(created_at=agora, paid_at=agora)
        return p

    def test_reembolsado_nao_fatura_e_conta_como_reembolsado(self):
        self._pedido('100.00')
        self._pedido('50.00', status='refunded', payment_status='refunded')
        self._pedido('30.00', status='cancelled', payment_status='cancelled')
        r = metrics.resumo_de_lista(StoreOrder.objects.filter(store=self.store))
        self.assertEqual(r['receita'], Decimal('100.00'))
        self.assertEqual(r['pedidos_faturados'], 1)
        self.assertEqual(r['cancelados'], 1)
        self.assertEqual(r['reembolsados'], 1)

    def test_reembolso_pelo_painel_deixa_o_pedido_entregue_mas_conta(self):
        # Reembolso pela cobrança: `status` fica 'delivered', só payment_status muda.
        self._pedido('80.00', status='delivered', payment_status='refunded')
        self._pedido('20.00', status='delivered', payment_status='partially_refunded')
        r = metrics.resumo_de_lista(StoreOrder.objects.filter(store=self.store))
        self.assertEqual(r['receita'], Decimal('0.00'))
        self.assertEqual(r['reembolsados'], 2)
        self.assertEqual(r['cancelados'], 0)
