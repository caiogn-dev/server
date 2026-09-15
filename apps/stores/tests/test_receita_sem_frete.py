"""Frete não é venda da loja: é repasse ao entregador.

Pedido do dono em 15/set/2026. Faturamento e ticket médio somavam `total`, que
inclui o frete. Na Cê Saladas em set/2026 o ticket aparecia R$ 64,88 quando a
venda real era R$ 57,44 — o frete era ~12% do "faturamento".

Cenário único em todos os testes: subtotal 60, frete 10, total 70.
Venda = 60. O caixa e o que o cliente pagou continuam 70.
"""
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder

User = get_user_model()


def _criar_pedido(loja, **extra):
    agora = timezone.now()
    dados = dict(
        store=loja, customer_name='Cliente', customer_phone='5563999000001',
        subtotal=Decimal('60.00'), delivery_fee=Decimal('10.00'), total=Decimal('70.00'),
        payment_status='paid', status='delivered', paid_at=agora, payment_method='pix',
        is_active=True,
    )
    dados.update(extra)
    pedido = StoreOrder.objects.create(**dados)
    pedido.refresh_from_db()
    assert pedido.total == Decimal('70.00'), pedido.total
    return pedido


class NucleoSemFreteTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-frete', password='x', email='df@real.com')
        self.loja = Store.objects.create(name='Loja Frete', slug='loja-frete', owner=self.dono, status='active')
        _criar_pedido(self.loja)

    def test_valor_de_venda_e_total_menos_frete(self):
        venda = StoreOrder.objects.annotate(v=metrics.valor_de_venda()).get(store=self.loja).v
        self.assertEqual(venda, Decimal('60.00'))

    def test_totais_sem_frete(self):
        t = metrics.totais(self.loja, metrics.hoje())
        self.assertEqual(t['receita'], Decimal('60.00'))
        self.assertEqual(t['ticket_medio'], Decimal('60.00'))
        self.assertEqual(t['frete'], Decimal('10.00'))

    def test_serie_temporal_sem_frete(self):
        (ponto,) = metrics.serie_temporal(self.loja, metrics.hoje())
        self.assertEqual(ponto['receita'], Decimal('60.00'))
        self.assertEqual(ponto['ticket_medio'], Decimal('60.00'))
        self.assertEqual(ponto['frete'], Decimal('10.00'))

    def test_resumo_de_lista_sem_frete(self):
        r = metrics.resumo_de_lista(StoreOrder.objects.filter(store=self.loja))
        self.assertEqual(r['receita'], Decimal('60.00'))
        self.assertEqual(r['ticket_medio'], Decimal('60.00'))
        self.assertEqual(r['frete'], Decimal('10.00'))

    def test_quebra_por_pagamento_continua_com_total_recebido(self):
        # "Como entrou o dinheiro": confere com a gaveta e o extrato, frete incluso.
        (linha,) = metrics.quebra_de_lista(StoreOrder.objects.filter(store=self.loja), 'payment_method')
        self.assertEqual(linha['total'], Decimal('70.00'))

    def test_gasto_do_cliente_sem_frete(self):
        from apps.stores.models import StoreCustomer
        cliente = StoreCustomer.objects.create(store=self.loja, user=self.dono)
        StoreOrder.objects.filter(store=self.loja).update(customer=self.dono)
        cliente.update_stats()
        self.assertEqual(cliente.total_spent, Decimal('60.00'))


class EndpointsSemFreteTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_superuser(username='dono-frete-api', password='x', email='dfa@real.com')
        self.loja = Store.objects.create(
            name='Loja Frete API', slug='loja-frete-api', owner=self.dono, status='active',
            billing_exempt=True,
        )
        _criar_pedido(self.loja)
        self.client.force_authenticate(self.dono)

    def test_overview_de_analytics(self):
        r = self.client.get('/api/v1/stores/reports/overview/', {'store': self.loja.slug, 'period': '7d'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertAlmostEqual(float(r.data['current']['revenue']), 60.0)
        self.assertAlmostEqual(float(r.data['current']['avg_ticket']), 60.0)

    def test_kpi_de_ticket_do_dashboard(self):
        r = self.client.get('/api/v1/core/dashboard/project-health/', {'store': self.loja.slug})
        self.assertEqual(r.status_code, 200, r.content)
        commerce = r.data['commerce']
        self.assertAlmostEqual(commerce['avg_ticket_month'], 60.0)
        self.assertAlmostEqual(commerce['revenue_today'], 60.0)

    def test_resumo_do_historico_de_pedidos(self):
        r = self.client.get('/api/v1/stores/orders/resumo/', {'store': self.loja.slug})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['faturamento'], '60.00')
        self.assertEqual(r.data['ticket_medio'], '60.00')
        self.assertEqual(r.data['frete'], '10.00')
        self.assertIn('sem frete', r.data['definicoes']['faturamento'])
        self.assertEqual(r.data['por_pagamento'][0]['total'], '70.00')

    def test_caixa_continua_com_frete(self):
        # A gaveta recebe o frete em dinheiro — o entregador é pago dali.
        from apps.stores.models import StoreCashSession
        sessao = StoreCashSession.objects.create(store=self.loja)
        StoreCashSession.objects.filter(pk=sessao.pk).update(
            opened_at=timezone.now() - timezone.timedelta(hours=1),
        )
        sessao.refresh_from_db()
        StoreOrder.objects.filter(store=self.loja).update(payment_method='cash')
        self.assertEqual(sessao.expected_cash(), Decimal('70.00'))
