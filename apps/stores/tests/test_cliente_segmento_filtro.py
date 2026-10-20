"""Lista de clientes filtra pelo segmento: VIP, ativos, em risco, inativos, nunca compraram.

O `stats` já contava "107 em risco, 30 a 45 dias sem comprar", mas a lista não
deixava ver QUEM são — o número aparecia e o lojista não tinha como agir sobre
ele. O admin do Prefiro resolve com abas acima da tabela; aqui é `?segmento=`.

A régua é a MESMA do `stats` (30/45 dias) e do `perfil` (VIP = 5+ pedidos):
aba que conta diferente do cartão de cima é a primeira coisa que o dono nota.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCustomer, StoreOrder

User = get_user_model()


def _pedido(loja, user, dias_atras):
    quando = timezone.now() - timedelta(days=dias_atras)
    p = StoreOrder.objects.create(
        store=loja, customer=user, total=Decimal('50'), subtotal=Decimal('50'),
        status=StoreOrder.OrderStatus.DELIVERED, payment_status=StoreOrder.PaymentStatus.PAID,
    )
    StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)


@pytest.fixture
def cenario(db):
    dono = User.objects.create_user(username='dono-seg', email='dono-seg@x.com', password='x')
    loja = Store.objects.create(name='Loja Seg', slug='loja-seg', owner=dono)

    def cliente(nome, *dias):
        u = User.objects.create_user(username=nome, email=f'{nome}@x.com', password='x')
        c = StoreCustomer.objects.create(store=loja, user=u)
        for d in dias:
            _pedido(loja, u, d)
        return c

    return {
        'loja': loja,
        'vip': cliente('vip', 2, 9, 16, 23, 30),       # 5 pedidos, último há 2 dias
        'ativo': cliente('ativo', 10),
        'risco': cliente('risco', 35),
        'inativo': cliente('inativo', 60),
        'lead': cliente('lead'),
    }


def _ids(cenario, segmento):
    api = APIClient()
    api.force_authenticate(user=cenario['loja'].owner)
    r = api.get('/api/v1/stores/customers/', {'store': cenario['loja'].slug, 'segmento': segmento})
    assert r.status_code == 200, r.content
    dados = r.json()
    linhas = dados['results'] if isinstance(dados, dict) else dados
    return {str(l['id']) for l in linhas}


@pytest.mark.django_db
@pytest.mark.parametrize('segmento,esperados', [
    ('vip', {'vip'}),
    ('ativos', {'vip', 'ativo'}),
    ('em_risco', {'risco'}),
    ('inativos', {'inativo'}),
    ('sem_compra', {'lead'}),
])
def test_filtra_pelo_segmento(cenario, segmento, esperados):
    assert _ids(cenario, segmento) == {str(cenario[k].id) for k in esperados}


@pytest.mark.django_db
def test_segmento_desconhecido_nao_esconde_ninguem(cenario):
    assert len(_ids(cenario, 'qualquer')) == 5


@pytest.mark.django_db
def test_stats_conta_vip_com_a_mesma_regua(cenario):
    api = APIClient()
    api.force_authenticate(user=cenario['loja'].owner)
    r = api.get('/api/v1/stores/customers/stats/', {'store': cenario['loja'].slug})
    seg = r.json()['segmentos']
    assert seg['vip'] == 1
    assert seg['reguas']['vip'] == '5 ou mais pedidos'
