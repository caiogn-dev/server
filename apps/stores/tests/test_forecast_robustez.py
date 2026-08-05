"""
A projeção não pode ser sequestrada por baixa manual em lote nem por um pico.

Caso real que motivou (loja Pastita, 04/08/2026): cinco pedidos de julho foram
marcados como pagos em 03/08 às 16:51 — todos no MESMO minuto, um deles com 26
dias de atraso. O `paid_at` do sistema não registra quando o dinheiro entrou;
registra quando alguém clicou "marcar como pago". Resultado: R$ 1.489 empilhados
num dia, inflando ao mesmo tempo a média recente, a tendência (+108%) e a
projeção do mês.

Quatro defesas:
  1. baixa em lote (mesmo paid_at ao segundo, N>=3) -> usa created_at
  2. mediana em vez de média para a média recente (robusta a outlier)
  3. sem percentual de tendência com amostra pequena
  4. dias com baixa retroativa não definem a projeção
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.stores.services.ai_insights import compute_forecast

User = get_user_model()
UTC = dt_timezone.utc


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_fc', password='x')
    return Store.objects.create(owner=dono, name='Loja FC', slug='loja-fc-test')


def _pedido(loja, total, criado, pago):
    o = StoreOrder.objects.create(
        store=loja, total=Decimal(str(total)), subtotal=Decimal(str(total)),
        status='delivered', payment_status='paid',
    )
    StoreOrder.objects.filter(pk=o.pk).update(created_at=criado, paid_at=pago)
    return o


@pytest.mark.django_db
class TestBaixaEmLote:

    def test_pedidos_marcados_no_mesmo_minuto_voltam_para_a_data_da_venda(self, loja):
        """O cenário da Pastita: 5 de julho baixados juntos em 03/08 16:51."""
        hoje = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
        lote = datetime(2026, 8, 3, 19, 51, tzinfo=UTC)  # 16:51 -03
        for dia in (8, 24, 28, 29, 29):
            _pedido(loja, 200, datetime(2026, 7, dia, 14, 0, tzinfo=UTC), lote)

        f = compute_forecast(loja, day=hoje.date())
        por_data = {d['date']: d['revenue'] for d in f['daily']}

        assert por_data.get('2026-08-03', 0) == 0, (
            f"a baixa em lote continuou empilhada em 03/08: {por_data.get('2026-08-03')}"
        )
        assert por_data.get('2026-07-29', 0) == 400, 'as duas vendas de 29/07 deveriam somar lá'
        assert por_data.get('2026-07-24', 0) == 200

    def test_pagamento_normal_continua_pela_data_do_pagamento(self, loja):
        """Baixa individual (não-lote) segue valendo como fluxo de caixa."""
        hoje = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
        _pedido(loja, 150,
                datetime(2026, 7, 31, 20, 0, tzinfo=UTC),
                datetime(2026, 8, 1, 14, 0, tzinfo=UTC))

        f = compute_forecast(loja, day=hoje.date())
        por_data = {d['date']: d['revenue'] for d in f['daily']}
        assert por_data.get('2026-08-01', 0) == 150, 'pagamento avulso deve ficar no dia do pagamento'
        assert por_data.get('2026-07-31', 0) == 0


@pytest.mark.django_db
class TestRobustezDaProjecao:

    def test_um_pico_nao_dita_a_projecao(self, loja):
        """Com 1 dia de R$ 3.000 e o resto vazio, a média mente; a mediana não."""
        hoje = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
        for i in range(6):
            d = datetime(2026, 8, 1 + i * 2, 14, 0, tzinfo=UTC)
            _pedido(loja, 100, d, d)
        pico = datetime(2026, 8, 18, 14, 0, tzinfo=UTC)
        _pedido(loja, 3000, pico, pico)

        f = compute_forecast(loja, day=hoje.date())
        # Média dos 14 dias recentes seria ~R$ 230/dia -> projeção estourada.
        assert f['month_projection'] < 4000, (
            f"projeção sequestrada pelo pico: R$ {f['month_projection']}"
        )
        assert f['month_projection'] >= f['month_realized']

    def test_amostra_pequena_nao_exibe_percentual(self, loja):
        """2 dias com venda em 28 não sustentam '+404%'."""
        hoje = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
        for d in (datetime(2026, 8, 18, 14, 0, tzinfo=UTC), datetime(2026, 8, 19, 14, 0, tzinfo=UTC)):
            _pedido(loja, 100, d, d)

        f = compute_forecast(loja, day=hoje.date())
        assert f['trend_reliable'] is False
        assert f['days_with_sale'] == 2

    def test_amostra_boa_exibe_percentual(self, loja):
        hoje = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
        for i in range(12):
            d = datetime(2026, 8, 5 + i, 14, 0, tzinfo=UTC)
            _pedido(loja, 100 + i * 10, d, d)

        f = compute_forecast(loja, day=hoje.date())
        assert f['trend_reliable'] is True
        assert f['days_with_sale'] >= 8
