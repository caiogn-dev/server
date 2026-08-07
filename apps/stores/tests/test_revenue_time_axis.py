"""
Receita é agrupada pela data em que o DINHEIRO ENTROU, no fuso da loja.

Dois defeitos técnicos que faziam o mesmo faturamento aparecer em dias
diferentes conforme a tela:

1. EIXO: `compute_forecast` agrupava por `created_at` e o painel por `paid_at`.
   Um pedido criado em 31/07 e pago em 01/08 caía em dias diferentes nas duas
   telas — o total batia, a distribuição não.

2. FUSO: `dashboard_views` usava `TruncDate(..., tzinfo=utc)` com o projeto em
   America/Sao_Paulo (-3h). Pedido pago às 22h de segunda entrava como terça.
   Latente porque só aparece com venda noturna — que é justamente o horário de
   pico de delivery.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreOrder
from apps.stores.metrics import eixo_de_receita, pedidos_de_receita

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_tz', password='x')
    return Store.objects.create(owner=dono, name='Loja TZ', slug='loja-tz-test')


def _pedido(loja, total, criado, pago):
    o = StoreOrder.objects.create(
        store=loja, total=Decimal(total), subtotal=Decimal(total),
        status='delivered', payment_status='paid',
    )
    StoreOrder.objects.filter(pk=o.pk).update(created_at=criado, paid_at=pago)
    return StoreOrder.objects.get(pk=o.pk)


@pytest.mark.django_db
class TestEixoDeReceita:

    def test_agrupa_pela_data_do_pagamento_nao_da_criacao(self, loja):
        """Pedido criado dia 31 e pago dia 1 é faturamento do dia 1."""
        criado = datetime(2026, 7, 31, 20, 0, tzinfo=dt_timezone.utc)
        pago = datetime(2026, 8, 1, 14, 0, tzinfo=dt_timezone.utc)
        _pedido(loja, '112.60', criado, pago)

        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        linhas = {
            r['d'].isoformat(): float(r['t'])
            for r in pedidos_de_receita(loja=loja)
            .annotate(d=TruncDate(eixo_de_receita()))
            .values('d').annotate(t=Sum('total'))
        }
        assert '2026-08-01' in linhas, f'esperava no dia do pagamento, veio {linhas}'
        assert '2026-07-31' not in linhas

    def test_usa_created_at_quando_nao_ha_paid_at(self, loja):
        """Pedido pago fora do gateway (dinheiro na entrega) não pode sumir."""
        criado = timezone.now() - timedelta(days=2)
        o = StoreOrder.objects.create(
            store=loja, total=Decimal('50.00'), subtotal=Decimal('50.00'),
            status='delivered', payment_status='paid',
        )
        StoreOrder.objects.filter(pk=o.pk).update(created_at=criado, paid_at=None)

        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        total = (
            pedidos_de_receita(loja=loja)
            .annotate(d=TruncDate(eixo_de_receita()))
            .values('d').annotate(t=Sum('total'))
        )
        assert len(total) == 1, 'pedido sem paid_at sumiu do agrupamento'
        assert float(total[0]['t']) == 50.0


@pytest.mark.django_db
class TestFusoHorario:

    def test_venda_da_noite_fica_no_dia_certo(self, loja):
        """22h de 03/08 em São Paulo = 01:00 UTC de 04/08.

        Agrupar em UTC jogaria essa venda para o dia seguinte — e é justamente o
        horário de pico do delivery.
        """
        pago_utc = datetime(2026, 8, 4, 1, 0, tzinfo=dt_timezone.utc)  # 03/08 22h -03
        _pedido(loja, '90.00', pago_utc, pago_utc)

        from django.db.models import Sum
        from django.db.models.functions import TruncDate
        # Sem tzinfo explícito o Django usa o TIME_ZONE do projeto.
        linhas = {
            r['d'].isoformat(): float(r['t'])
            for r in pedidos_de_receita(loja=loja)
            .annotate(d=TruncDate(eixo_de_receita()))
            .values('d').annotate(t=Sum('total'))
        }
        assert '2026-08-03' in linhas, f'venda das 22h caiu no dia errado: {linhas}'
        assert '2026-08-04' not in linhas
