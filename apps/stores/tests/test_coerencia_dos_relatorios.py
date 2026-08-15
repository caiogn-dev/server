"""Todas as telas dizem o MESMO número para o mesmo período.

A divergência entre telas não nasce de conta errada — nasce de cada tela poder
escolher a sua regra em silêncio. `apps/stores/metrics/__init__.py` já diz, no
próprio docstring, que "nenhuma view deve conter `Sum('total')`". A regra
existia e não era cobrada.

Este teste é o cobrador. Sem ele, a próxima tela inventa a regra dela e o
conserto envelhece em duas semanas.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores import metrics
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def vendas(loja):
    """Um cenário com tudo que costuma confundir relatório."""
    agora = timezone.now()
    feito = []
    for valor, status, pago in [
        ('100.00', 'delivered', 'paid'),      # conta
        ('50.00', 'delivered', 'paid'),       # conta
        ('30.00', 'cancelled', 'paid'),       # NÃO conta: cancelado
        ('20.00', 'delivered', 'pending'),    # NÃO conta: não pago
    ]:
        p = StoreOrder.objects.create(
            store=loja, total=Decimal(valor), subtotal=Decimal(valor),
            status=status, payment_status=pago, payment_method='pix',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)
        feito.append(p)
    return feito


@pytest.fixture
def cliente_api(loja):
    U = get_user_model()
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


@pytest.mark.django_db
class TestTodasAsTelasConcordam:
    def _janela(self):
        hoje = timezone.localdate()
        return hoje, hoje

    def test_referencia_conta_so_o_que_deve(self, loja, vendas):
        inicio, fim = self._janela()

        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        assert t['receita'] == Decimal('150.00')
        assert t['pedidos'] == 2

    def test_reports_revenue_bate_com_a_referencia(self, loja, vendas, cliente_api):
        inicio, fim = self._janela()
        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        r = cliente_api.get(
            '/api/v1/stores/reports/revenue/',
            {'store': loja.slug, 'start_date': str(inicio), 'end_date': str(fim)},
        )

        assert r.status_code == 200
        assert Decimal(str(r.data['summary']['total_revenue'])) == t['receita']
        assert r.data['summary']['total_orders'] == t['pedidos']

    def test_dashboard_bate_com_a_referencia(self, loja, vendas, cliente_api):
        """O bug: 'orders' contava TODOS e 'revenue' só os pagos."""
        janela = metrics.mes_corrente()
        t = metrics.totais(loja, janela)

        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})

        assert r.status_code == 200
        assert Decimal(str(r.data['month']['revenue'])) == t['receita']
        assert r.data['month']['orders'] == t['pedidos'], (
            'o cartão conta pedidos por uma regra e receita por outra'
        )

    def test_o_ticket_do_cartao_e_divisivel(self, loja, vendas, cliente_api):
        """É a leitura que o cartão convida a fazer — tem que fechar."""
        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})
        mes = r.data['month']

        esperado = Decimal(str(mes['revenue'])) / mes['orders']

        assert abs(esperado - Decimal('75.00')) < Decimal('0.01')


@pytest.mark.django_db
class TestOsRotulosDizemAVerdade:
    def test_month_e_o_mes_do_calendario(self, loja, vendas, cliente_api):
        """'month' usava `hoje - 30 dias`. Para o dono, mês tem primeiro dia."""
        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})

        janela = metrics.mes_corrente()
        assert Decimal(str(r.data['month']['revenue'])) == metrics.totais(
            loja, janela,
        )['receita']


@pytest.mark.django_db
class TestAsOutrasSuperficies:
    """O spec lista seis superfícies. Estas três têm recorte próprio, e o teste
    respeita o recorte em vez de exigir igualdade cega — exigir que o caixa
    bata com o faturamento total seria errado: o caixa é só a gaveta.
    """

    def test_a_exportacao_de_pedidos_traz_os_mesmos_pedidos(self, loja, vendas, cliente_api):
        inicio = fim = timezone.localdate()
        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        r = cliente_api.get(
            '/api/v1/stores/reports/orders/export/',
            {'store': loja.slug, 'start_date': str(inicio), 'end_date': str(fim),
             'somente_receita': '1'},
        )

        assert r.status_code == 200
        linhas = [l for l in r.content.decode().splitlines() if l.strip()]
        # cabeçalho + uma linha por pedido de receita
        assert len(linhas) - 1 == t['pedidos'], (
            'a exportação traz um conjunto diferente do faturamento'
        )

    def test_o_caixa_conta_so_a_gaveta(self, loja):
        """Recorte próprio e correto: só dinheiro, só na janela da sessão.

        Não deve bater com o faturamento total — deve bater com a parte dele
        que é dinheiro. Confundir os dois faz o fechamento acusar quebra que
        não existe.
        """
        from apps.stores.models import StoreCashSession

        agora = timezone.now()
        sessao = StoreCashSession.objects.create(
            store=loja, opened_at=agora - timezone.timedelta(hours=1),
            opening_amount=Decimal('0.00'), status='open',
        )
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('40.00'), subtotal=Decimal('40.00'),
            status='delivered', payment_status='paid', payment_method='cash',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)

        assert sessao.expected_amount == Decimal('40.00')

    def test_o_caixa_ignora_pix(self, loja):
        """PIX não entra na gaveta — é o recorte que justifica o filtro."""
        from apps.stores.models import StoreCashSession

        agora = timezone.now()
        sessao = StoreCashSession.objects.create(
            store=loja, opened_at=agora - timezone.timedelta(hours=1),
            opening_amount=Decimal('0.00'), status='open',
        )
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('40.00'), subtotal=Decimal('40.00'),
            status='delivered', payment_status='paid', payment_method='pix',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)

        assert sessao.expected_amount == Decimal('0.00')
