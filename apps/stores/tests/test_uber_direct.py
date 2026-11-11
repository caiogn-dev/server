"""Uber Direct: cotação no formato da API real + modo sombra + resumo.

Origem (11/11/2026): o cliente antigo (`apps/orders/services/uber_delivery.py`)
mandava `pickup: {...}` como objeto e lia `delivery_request_id` — formato que o
Direct não aceita. 583 pedidos, 0 despachados. Antes de ligar despacho de
verdade, o dono quer saber quanto a Uber cobraria contra o frete que o cliente
pagou: o modo sombra só cota e grava, nunca chama entregador.
"""
import json
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder, UberCotacao
from apps.stores.services.delivery_provider.uber_direct import UberDirectProvider

User = get_user_model()

COTACAO_OK = {
    'kind': 'delivery_quote', 'id': 'dqt_abc', 'fee': 1810, 'currency': 'brl',
    'duration': 46, 'pickup_duration': 11, 'expires': '2026-11-11T18:03:39.55Z',
}


def _resp(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.json.return_value = body or {}
    r.text = json.dumps(body or {})
    return r


@pytest.fixture
def credenciais(settings, monkeypatch):
    monkeypatch.setenv('UBER_CUSTOMER_ID', 'cus-123')
    monkeypatch.setenv('UBER_API_KEY', 'cid')
    monkeypatch.setenv('UBER_CLIENT_SECRET', 'sec')


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='uberdono', email='u@x.com', password='x')
    return Store.objects.create(
        name='Cê Teste', slug='ce-teste-uber', owner=dono, status='active',
        phone='63999990000', address='Quadra 104 Norte, Avenida LO 2',
        city='Palmas', state='TO', zip_code='77006-022',
        latitude=Decimal('-10.1800000'), longitude=Decimal('-48.3300000'),
    )


def _pedido(loja, **extra):
    dados = dict(
        store=loja, customer_name='Maria', customer_phone='63988887777',
        subtotal=Decimal('40.00'), total=Decimal('48.00'), delivery_fee=Decimal('8.00'),
        delivery_method='delivery',
        delivery_address={
            'street': 'Quadra 403 Sul, Alameda 10', 'number': '12', 'complement': 'casa 2',
            'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO',
            'zip_code': '77015-570',
        },
        delivery_lat=Decimal('-10.2300000'), delivery_lng=Decimal('-48.3200000'),
    )
    dados.update(extra)
    return StoreOrder.objects.create(**dados)


def _com_token(post_mock, *respostas):
    """Primeira chamada = token; as seguintes = API."""
    post_mock.side_effect = [_resp(200, {'access_token': 'tok', 'expires_in': 3600}), *respostas]


@pytest.mark.django_db
def test_cotacao_vai_no_formato_do_direct(loja, credenciais):
    pedido = _pedido(loja)
    with mock.patch('apps.stores.services.delivery_provider.uber_direct.requests.post') as post:
        _com_token(post, _resp(200, COTACAO_OK))
        cot = UberDirectProvider().cotar(loja, pedido)

    token_call, quote_call = post.call_args_list
    assert token_call.kwargs['data']['scope'] == 'eats.deliveries'
    assert quote_call.args[0] == 'https://api.uber.com/v1/customers/cus-123/delivery_quotes'
    corpo = quote_call.kwargs['json']
    # O Direct quer o endereço como STRING JSON, não objeto.
    coleta = json.loads(corpo['pickup_address'])
    entrega = json.loads(corpo['dropoff_address'])
    assert coleta['street_address'][0] == 'Quadra 104 Norte, Avenida LO 2'
    assert coleta['city'] == 'Palmas' and coleta['country'] == 'BR'
    assert entrega['street_address'] == ['Quadra 403 Sul, Alameda 10, 12', 'casa 2']
    assert entrega['zip_code'] == '77015-570'
    assert corpo['dropoff_latitude'] == pytest.approx(-10.23)
    assert corpo['pickup_longitude'] == pytest.approx(-48.33)

    assert cot['quote_id'] == 'dqt_abc'
    assert cot['fee'] == Decimal('18.10')
    assert cot['duracao_min'] == 46 and cot['coleta_min'] == 11


@pytest.mark.django_db
def test_sombra_grava_cotacao_contra_frete_cobrado_e_nao_duplica(loja, credenciais):
    from apps.stores.tasks import cotar_uber_sombra

    pedido = _pedido(loja)
    with mock.patch('apps.stores.services.delivery_provider.uber_direct.requests.post') as post:
        _com_token(post, _resp(200, COTACAO_OK))
        cotar_uber_sombra(str(pedido.id))
        cotar_uber_sombra(str(pedido.id))  # retry/duplo aviso não cota de novo

    cots = UberCotacao.objects.filter(order=pedido)
    assert cots.count() == 1
    c = cots.get()
    assert c.origem == 'sombra'
    assert c.fee == Decimal('18.10')
    assert c.taxa_cobrada == Decimal('8.00')
    assert c.diferenca == Decimal('10.10')  # quanto a loja perderia
    assert Decimal('5.0') < c.distancia_km < Decimal('6.5')  # linha reta loja→cliente
    assert c.erro == ''
    # Sombra NUNCA despacha: só uma chamada de cotação, nenhuma em /deliveries.
    assert not any(ca.args and ca.args[0].endswith('/deliveries') for ca in post.call_args_list)


@pytest.mark.django_db
def test_erro_da_uber_fica_registrado_sem_quebrar(loja, credenciais):
    from apps.stores.tasks import cotar_uber_sombra

    pedido = _pedido(loja)
    with mock.patch('apps.stores.services.delivery_provider.uber_direct.requests.post') as post:
        _com_token(post, _resp(400, {'code': 'address_undeliverable', 'message': 'fora da área'}))
        cotar_uber_sombra(str(pedido.id))

    c = UberCotacao.objects.get(order=pedido)
    assert c.fee is None
    assert 'address_undeliverable' in c.erro


@pytest.mark.django_db(transaction=False)
def test_pedido_de_entrega_dispara_sombra_so_na_loja_ligada(loja, django_capture_on_commit_callbacks):
    with mock.patch('apps.stores.tasks.cotar_uber_sombra.delay') as delay:
        with django_capture_on_commit_callbacks(execute=True):
            _pedido(loja)
        assert delay.call_count == 0

        loja.metadata = {'uber_sombra': True}
        loja.save(update_fields=['metadata'])
        with django_capture_on_commit_callbacks(execute=True):
            p = _pedido(loja)
            _pedido(loja, delivery_method='pickup', delivery_fee=Decimal('0'))
        assert [c.args[0] for c in delay.call_args_list] == [str(p.id)]


@pytest.mark.django_db
def test_resumo_por_faixa_de_km(loja):
    from apps.stores.services.uber_resumo import resumo_por_faixa

    def cot(km, fee, cobrada):
        UberCotacao.objects.create(
            store=loja, origem='historico', distancia_km=Decimal(km),
            fee=Decimal(fee), taxa_cobrada=Decimal(cobrada),
        )

    for fee in ('10', '12', '14', '16'):
        cot('2.0', fee, '8')
    cot('5.5', '18.10', '12')
    UberCotacao.objects.create(store=loja, origem='historico', erro='x')  # não entra

    faixas = {f['faixa']: f for f in resumo_por_faixa(UberCotacao.objects.filter(store=loja))}
    f = faixas['0–3 km']
    assert f['n'] == 4
    assert f['media_uber'] == Decimal('13.00')
    assert f['p75_uber'] == Decimal('14.50')
    assert f['media_cobrada'] == Decimal('8.00')
    assert f['no_prejuizo'] == 4
    assert faixas['5–7 km']['n'] == 1


@pytest.mark.django_db
def test_criar_entrega_no_formato_do_direct(loja, credenciais):
    pedido = _pedido(loja)
    with mock.patch('apps.stores.services.delivery_provider.uber_direct.requests.post') as post:
        _com_token(post, _resp(200, {
            'id': 'del_xyz', 'status': 'pending', 'tracking_url': 'https://track/x', 'fee': 1810,
        }))
        r = UberDirectProvider().create(loja, pedido, quote_id='dqt_abc')

    corpo = post.call_args_list[1].kwargs['json']
    assert post.call_args_list[1].args[0] == 'https://api.uber.com/v1/customers/cus-123/deliveries'
    assert corpo['quote_id'] == 'dqt_abc'
    assert corpo['pickup_name'] == 'Cê Teste'
    assert corpo['pickup_phone_number'] == '+5563999990000'   # loja, não o cliente
    assert corpo['dropoff_phone_number'] == '+5563988887777'
    assert corpo['dropoff_name'] == 'Maria'
    assert corpo['external_id'] == pedido.order_number
    assert corpo['manifest_items']
    assert r.external_id == 'del_xyz'
    assert r.tracking_url == 'https://track/x'


def test_status_da_uber_vira_status_do_pedido():
    p = UberDirectProvider()
    assert p.map_status_to_order('pending') is None
    assert p.map_status_to_order('pickup') is None
    assert p.map_status_to_order('pickup_complete') == 'out_for_delivery'
    assert p.map_status_to_order('dropoff') == 'out_for_delivery'
    assert p.map_status_to_order('delivered') == 'delivered'
    assert p.map_status_to_order('canceled') is None  # cancelamento pede decisão humana


@pytest.mark.django_db
def test_comando_cota_historico_uma_vez_e_mostra_resumo(loja, credenciais, capsys):
    from django.core.management import call_command

    a = _pedido(loja)
    b = _pedido(loja)
    _pedido(loja, delivery_method='pickup', delivery_fee=Decimal('0'))
    _pedido(loja, status='cancelled')  # cancelado não conta
    UberCotacao.objects.create(store=loja, order=b, origem='historico', fee=Decimal('15'),
                               taxa_cobrada=Decimal('8'), distancia_km=Decimal('5.6'))

    with mock.patch('apps.stores.services.delivery_provider.uber_direct.requests.post') as post, \
            mock.patch('apps.stores.management.commands.cotar_uber_historico.time.sleep'):
        _com_token(post, _resp(200, COTACAO_OK))
        call_command('cotar_uber_historico', loja=loja.slug, dias=30)

    assert set(UberCotacao.objects.filter(store=loja).values_list('order_id', flat=True)) == {a.id, b.id}
    saida = capsys.readouterr().out
    assert '5–7 km' in saida and 'P75' in saida
