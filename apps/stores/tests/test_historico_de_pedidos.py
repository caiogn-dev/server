"""A guia de histórico: todos os pedidos, com filtro de período.

O painel tinha o kanban do dia (operação) e o detalhe de um pedido. Não tinha
onde responder "o que eu vendi na semana passada" — a pergunta que aparece
quando o dono senta para fechar o mês, conferir uma reclamação de duas semanas
atrás ou achar o pedido de um cliente que ligou.

TRÊS DECISÕES QUE OS TESTES FIXAM:

1. O período filtra por `created_at` NO FUSO DA LOJA. `__date` sobre UTC joga
   tudo que foi vendido depois das 21h para o dia seguinte — e 21h é o pico do
   delivery. Foi exatamente esse bug no card "Receita hoje" em 06/ago.

2. O resumo soma OS PEDIDOS DA LISTA, não uma consulta paralela. Se o KPI diz
   R$ 900 e somar as linhas dá R$ 850, a tela inteira perde credibilidade —
   e a divergência vem justamente de somar por `paid_at` e listar por
   `created_at`.

3. Cancelado APARECE na lista e NÃO entra no faturamento. Sumir com ele
   esconderia o que o dono mais quer investigar; somá-lo inflaria a receita.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.metrics import hoje_local
from apps.stores.models import Store, StoreOrder

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-hist', email='dono-hist@x.com', password='x')
    return Store.objects.create(name='Loja Histórico', slug='loja-hist', owner=dono)


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(user=loja.owner)
    return c


def _pedido(loja, total, dias_atras=0, status=None, payment_status=None, nome='Cliente', **extra):
    p = StoreOrder.objects.create(
        store=loja,
        customer_name=nome,
        customer_phone='63999990000',
        subtotal=Decimal(str(total)),
        total=Decimal(str(total)),
        status=status or StoreOrder.OrderStatus.DELIVERED,
        payment_status=payment_status or StoreOrder.PaymentStatus.PAID,
        **extra,
    )
    quando = timezone.now() - timedelta(days=dias_atras)
    # created_at é auto_now_add: só dá para posicionar no tempo com update().
    StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)
    p.refresh_from_db()
    return p


def _listar(api, loja, **params):
    r = api.get('/api/v1/stores/orders/', {'store': loja.slug, **params})
    assert r.status_code == 200, r.content
    d = r.json()
    return d['results'] if isinstance(d, dict) and 'results' in d else d


@pytest.mark.django_db
class TestFiltroDePeriodo:
    def test_recorta_pelo_periodo_pedido(self, api, loja):
        _pedido(loja, 10, dias_atras=0, nome='Hoje')
        _pedido(loja, 20, dias_atras=3, nome='Semana')
        _pedido(loja, 30, dias_atras=40, nome='Mês passado')

        hoje = hoje_local()
        linhas = _listar(
            api, loja,
            date_from=(hoje - timedelta(days=7)).isoformat(),
            date_to=hoje.isoformat(),
        )
        nomes = {l['customer_name'] for l in linhas}
        assert nomes == {'Hoje', 'Semana'}

    def test_so_o_inicio_ja_filtra(self, api, loja):
        # Quem digita "de 01/08" sem preencher o fim quer "de lá para cá", não
        # um erro de validação.
        _pedido(loja, 10, dias_atras=1, nome='Recente')
        _pedido(loja, 20, dias_atras=60, nome='Antigo')

        linhas = _listar(api, loja, date_from=(hoje_local() - timedelta(days=7)).isoformat())
        assert {l['customer_name'] for l in linhas} == {'Recente'}

    def test_o_dia_final_entra_inteiro(self, api, loja):
        # Filtro de fim que corta em 00:00 perde o dia todo. Quem pede
        # "até hoje" quer as vendas de hoje inclusive.
        _pedido(loja, 10, dias_atras=0, nome='Hoje')
        hoje = hoje_local()
        linhas = _listar(api, loja, date_from=hoje.isoformat(), date_to=hoje.isoformat())
        assert len(linhas) == 1

    def test_data_invalida_nao_derruba_a_pagina(self, api, loja):
        # Vem de URL colada e de campo de texto. 500 aqui apaga a tela inteira;
        # ignorar o filtro devolve a lista completa, que é recuperável.
        _pedido(loja, 10)
        linhas = _listar(api, loja, date_from='ontem')
        assert len(linhas) == 1

    def test_cancelado_continua_na_lista(self, api, loja):
        # É o pedido que o dono MAIS quer achar no histórico.
        _pedido(loja, 50, status=StoreOrder.OrderStatus.CANCELLED, nome='Cancelado')
        linhas = _listar(api, loja)
        assert {l['customer_name'] for l in linhas} == {'Cancelado'}


@pytest.mark.django_db
class TestResumoDoPeriodo:
    def _resumo(self, api, loja, **params):
        r = api.get('/api/v1/stores/orders/resumo/', {'store': loja.slug, **params})
        assert r.status_code == 200, r.content
        return r.json()

    def test_resumo_bate_com_a_soma_das_linhas(self, api, loja):
        _pedido(loja, 100, dias_atras=1)
        _pedido(loja, 50, dias_atras=2)

        hoje = hoje_local()
        d = self._resumo(api, loja, date_from=(hoje - timedelta(days=7)).isoformat(), date_to=hoje.isoformat())
        assert d['pedidos'] == 2
        assert Decimal(d['faturamento']) == Decimal('150.00')

    def test_cancelado_conta_como_pedido_mas_nao_como_dinheiro(self, api, loja):
        _pedido(loja, 100)
        _pedido(loja, 999, status=StoreOrder.OrderStatus.CANCELLED)

        d = self._resumo(api, loja)
        assert d['pedidos'] == 2
        assert Decimal(d['faturamento']) == Decimal('100.00')
        assert d['cancelados'] == 1

    def test_ticket_medio_divide_pelos_pedidos_que_FATURARAM(self, api, loja):
        # Dividir por todos os pedidos (incluindo cancelado e não pago) faria o
        # ticket despencar e mentir sobre o tamanho da venda média.
        _pedido(loja, 100)
        _pedido(loja, 200)
        _pedido(loja, 999, status=StoreOrder.OrderStatus.CANCELLED)
        _pedido(loja, 999, payment_status=StoreOrder.PaymentStatus.PENDING)

        d = self._resumo(api, loja)
        assert Decimal(d['ticket_medio']) == Decimal('150.00')

    def test_periodo_sem_venda_devolve_zero_sem_quebrar(self, api, loja):
        d = self._resumo(api, loja, date_from='2020-01-01', date_to='2020-01-31')
        assert d['pedidos'] == 0
        assert Decimal(d['faturamento']) == Decimal('0.00')
        # `null` e não `0.00`: "ticket médio R$ 0,00" lê como venda de graça.
        assert d['ticket_medio'] is None

    def test_resumo_respeita_o_mesmo_filtro_da_lista(self, api, loja):
        # Se o resumo ignorasse `status`, o dono filtraria "cancelados" e veria
        # o faturamento do período inteiro no card acima da lista.
        _pedido(loja, 100)
        _pedido(loja, 40, status=StoreOrder.OrderStatus.CANCELLED)

        d = self._resumo(api, loja, status=StoreOrder.OrderStatus.CANCELLED)
        assert d['pedidos'] == 1
        assert Decimal(d['faturamento']) == Decimal('0.00')

    def test_quebra_por_pagamento_ajuda_a_fechar_o_caixa(self, api, loja):
        _pedido(loja, 100, payment_method='pix')
        _pedido(loja, 60, payment_method='pix')
        _pedido(loja, 40, payment_method='cash')

        d = self._resumo(api, loja)
        por_pgto = {x['chave']: x for x in d['por_pagamento']}
        assert Decimal(por_pgto['pix']['total']) == Decimal('160.00')
        assert por_pgto['pix']['pedidos'] == 2
        assert Decimal(por_pgto['cash']['total']) == Decimal('40.00')
