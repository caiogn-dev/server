"""Relatórios › Vendas: todos os cards falam do MESMO período.

Bug de 06/11: com "Ontem" selecionado, "Pedidos no período" mostrava pedidos de
HOJE e "Cancelados" o total desde sempre (71 — "7100,0% do total"). Esses cards,
"Pedidos por dia" e "Distribuição por status" liam `core/dashboard/charts/?days=1`,
que não conhece o período; faturamento e ticket liam `reports/revenue/`.

Agora `reports/revenue/` devolve também o bloco `vendas`, calculado pela MESMA
regra do Histórico de pedidos (`/orders/resumo/`), na MESMA janela.

Gabarito (Cê, 05/11): 20 pedidos, 18 pagos, 2 cancelados, R$ 496,37,
ticket R$ 27,58 (= receita ÷ 18).
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores import metrics
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store

URL = '/api/v1/stores/reports/revenue/'


def _local(dia, hora, minuto=0):
    return timezone.make_aware(
        datetime.combine(dia, time(hora, minuto)), timezone.get_current_timezone(),
    )


def _pedido(loja, quando, venda, frete='0.00', status='delivered', pago='paid', **extra):
    venda, frete = Decimal(venda), Decimal(frete)
    p = StoreOrder.objects.create(
        store=loja, subtotal=venda, delivery_fee=frete, total=venda + frete,
        status=status, payment_status=pago, payment_method='pix',
        customer_phone='+5563984143551', **extra,
    )
    StoreOrder.objects.filter(id=p.id).update(created_at=quando, paid_at=quando)
    return p


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


@pytest.fixture
def ontem():
    return metrics.hoje_local() - timedelta(days=1)


@pytest.fixture
def dia_da_ce(loja, ontem):
    """20 pedidos ontem (18 pagos, 2 cancelados) + ruído fora do período."""
    hoje = ontem + timedelta(days=1)
    # 17 × 27,00 + 1 × 37,37 = 496,37 de venda (frete à parte, não é venda).
    for i in range(17):
        _pedido(loja, _local(ontem, 11, i), '27.00', frete='5.00')
    # 23h30 local = 02h30 UTC do dia seguinte: tem que ficar em ONTEM.
    _pedido(loja, _local(ontem, 23, 30), '37.37', frete='7.00')
    _pedido(loja, _local(ontem, 12), '40.00', status='cancelled', pago='pending')
    _pedido(loja, _local(ontem, 13), '55.00', status='cancelled', pago='paid')

    # Fora do período: hoje (inclusive 00h30, que em UTC ainda é "ontem")…
    _pedido(loja, _local(hoje, 0, 30), '99.00')
    _pedido(loja, _local(hoje, 12), '99.00', status='cancelled', pago='pending')
    # …e cancelados antigos, que eram somados no card "desde sempre".
    for d in range(2, 40):
        _pedido(loja, _local(ontem - timedelta(days=d), 12), '10.00',
                status='cancelled', pago='pending')
    # Venda de saldo (carteira) não aparece no Histórico — também não aqui.
    _pedido(loja, _local(ontem, 15), '100.00', source='carteira')


def _vendas(api, loja, **params):
    r = api.get(URL, {'store': loja.slug, **params})
    assert r.status_code == 200, r.content
    return r.json()['vendas']


@pytest.mark.django_db
class TestGabaritoDoDia:
    def test_ontem_bate_com_o_gabarito(self, api, loja, dia_da_ce):
        v = _vendas(api, loja, period='ontem')

        assert v['pedidos'] == 20
        assert v['pagos'] == 18
        assert v['cancelados'] == 2
        assert Decimal(v['faturamento']) == Decimal('496.37')
        assert Decimal(v['ticket_medio']) == Decimal('27.58')  # 496,37 ÷ 18

    def test_personalizado_igual_a_ontem(self, api, loja, dia_da_ce, ontem):
        v = _vendas(api, loja, start_date=str(ontem), end_date=str(ontem))

        assert (v['pedidos'], v['pagos'], v['cancelados']) == (20, 18, 2)
        assert Decimal(v['ticket_medio']) == Decimal('27.58')

    def test_percentual_de_cancelados_e_do_periodo(self, api, loja, dia_da_ce):
        v = _vendas(api, loja, period='ontem')

        assert v['cancelados_pct'] == 10.0  # 2 ÷ 20
        assert 0 <= v['cancelados_pct'] <= 100

    def test_distribuicao_por_status_soma_os_pedidos_do_periodo(self, api, loja, dia_da_ce):
        v = _vendas(api, loja, period='ontem')

        assert v['por_status'] == {'delivered': 18, 'cancelled': 2}
        assert sum(v['por_status'].values()) == v['pedidos']

    def test_pedidos_por_dia_so_tem_o_periodo(self, api, loja, dia_da_ce, ontem):
        v = _vendas(api, loja, period='ontem')

        assert v['por_dia'] == [
            {'date': str(ontem), 'pedidos': 20, 'pagos': 18, 'cancelados': 2,
             'faturamento': '496.37'},
        ]

    def test_por_dia_preenche_dia_sem_pedido_com_zero(self, api, loja, dia_da_ce, ontem):
        anteontem = ontem - timedelta(days=1)
        v = _vendas(api, loja, start_date=str(anteontem - timedelta(days=1)),
                    end_date=str(ontem))

        dias = [d['date'] for d in v['por_dia']]
        assert dias == [str(anteontem - timedelta(days=1)), str(anteontem), str(ontem)]
        assert v['por_dia'][0]['pedidos'] == 1  # só o cancelado antigo
        assert sum(d['pedidos'] for d in v['por_dia']) == v['pedidos']


@pytest.mark.django_db
class TestMesmaRegraDoHistorico:
    def test_igual_ao_resumo_do_historico(self, api, loja, dia_da_ce, ontem):
        v = _vendas(api, loja, period='ontem')
        h = api.get('/api/v1/stores/orders/resumo/', {
            'store': loja.slug, 'date_from': str(ontem), 'date_to': str(ontem),
        }).json()

        assert v['pedidos'] == h['pedidos']
        assert v['pagos'] == h['pedidos_faturados']
        assert v['cancelados'] == h['cancelados']
        assert v['faturamento'] == h['faturamento']
        assert v['ticket_medio'] == h['ticket_medio']

    def test_pedido_de_teste_nao_fatura(self, api, loja, ontem):
        _pedido(loja, _local(ontem, 10), '50.00')
        _pedido(loja, _local(ontem, 11), '80.00', metadata={'is_test': True})

        v = _vendas(api, loja, period='ontem')

        assert v['pagos'] == 1
        assert Decimal(v['faturamento']) == Decimal('50.00')


@pytest.mark.django_db
class TestPeriodoVazio:
    def test_sem_pedidos_nao_divide_por_zero(self, api, loja):
        v = _vendas(api, loja, period='hoje')

        assert v['pedidos'] == 0
        assert v['cancelados_pct'] == 0
        assert v['ticket_medio'] is None
        assert v['por_status'] == {}


@pytest.mark.django_db
class TestServicoReutilizavel:
    def test_servico_responde_sem_view(self, loja, dia_da_ce, ontem):
        v = metrics.vendas_do_periodo(loja, metrics.de_datas(ontem, ontem))

        assert (v['pedidos'], v['pagos'], v['cancelados']) == (20, 18, 2)
        assert v['faturamento'] == Decimal('496.37')
        assert v['ticket_medio'] == Decimal('27.58')
