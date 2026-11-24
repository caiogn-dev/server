"""Carteira de cartões (estilo iFood) na conta Mercado Pago da PLATAFORMA.

O MP nunca é chamado de verdade: `cartoes_salvos._mp` é substituído por um
falso que registra as chamadas.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.models import UserProfile
from apps.stores.services import cartoes_salvos
from apps.stores.tests.factories import make_store

User = get_user_model()

CARTAO_MP = {
    'id': 'card-1',
    'last_four_digits': '6351',
    'first_six_digits': '503143',
    'expiration_month': 11,
    'expiration_year': 2030,
    'payment_method': {'id': 'master', 'payment_type_id': 'credit_card'},
    'security_code': {'length': 3},
    'issuer': {'id': 1, 'name': 'Mastercard'},
}


class MPFalso:
    def __init__(self, respostas=None):
        self.chamadas = []
        self.respostas = respostas or {}

    def __call__(self, metodo, caminho, json=None, params=None):
        self.chamadas.append((metodo, caminho, json, params))
        for (m, prefixo), resp in self.respostas.items():
            if m == metodo and caminho.startswith(prefixo):
                return resp
        return 200, {}


@pytest.fixture
def usuario(db):
    u = User.objects.create_user(username='cli-1', password='x', email='cli@exemplo.com', first_name='Ana')
    UserProfile.objects.get_or_create(user=u)
    return u


@pytest.fixture
def loja_plataforma(db):
    return make_store(usa_gateway_da_plataforma=True)


def test_sem_cliente_no_mp_lista_vazia_sem_chamar_o_mp(usuario, monkeypatch):
    mp = MPFalso()
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)
    assert cartoes_salvos.listar(usuario) == []
    assert mp.chamadas == []


def test_salvar_cria_cliente_e_guarda_o_id(usuario, monkeypatch):
    mp = MPFalso({
        ('GET', '/v1/customers/search'): (200, {'results': []}),
        ('POST', '/v1/customers/cus-9/cards'): (201, CARTAO_MP),
        ('POST', '/v1/customers'): (201, {'id': 'cus-9'}),
    })
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)

    cartao = cartoes_salvos.salvar(usuario, 'tok-1')

    assert cartao == {
        'id': 'card-1', 'bandeira': 'master', 'tipo': 'credit_card', 'final': '6351',
        'validade': '11/30', 'cvv': 3,
    }
    usuario.profile.refresh_from_db()
    assert usuario.profile.mp_customer_id == 'cus-9'
    criar = [c for c in mp.chamadas if c[:2] == ('POST', '/v1/customers')][0]
    assert criar[2]['email'] == 'cli@exemplo.com'
    salvar = [c for c in mp.chamadas if c[1] == '/v1/customers/cus-9/cards'][0]
    assert salvar[2] == {'token': 'tok-1'}


def test_salvar_reaproveita_cliente_existente_no_mp(usuario, monkeypatch):
    mp = MPFalso({
        ('GET', '/v1/customers/search'): (200, {'results': [{'id': 'cus-antigo'}]}),
        ('POST', '/v1/customers/cus-antigo/cards'): (201, CARTAO_MP),
    })
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)
    cartoes_salvos.salvar(usuario, 'tok')
    assert not any(c[:2] == ('POST', '/v1/customers') for c in mp.chamadas)
    usuario.profile.refresh_from_db()
    assert usuario.profile.mp_customer_id == 'cus-antigo'


def test_cliente_sem_email_usa_email_tecnico(db, monkeypatch):
    u = User.objects.create_user(username='5563999990000', password='x', email='')
    mp = MPFalso({
        ('GET', '/v1/customers/search'): (200, {'results': []}),
        ('POST', '/v1/customers/c/cards'): (201, CARTAO_MP),
        ('POST', '/v1/customers'): (201, {'id': 'c'}),
    })
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)
    cartoes_salvos.salvar(u, 'tok')
    criar = [c for c in mp.chamadas if c[:2] == ('POST', '/v1/customers')][0]
    assert criar[2]['email'] == f'cliente-{u.pk}@clientes.cardapidex.com.br'


def test_recusa_do_mp_vira_erro_legivel(usuario, monkeypatch):
    usuario.profile.mp_customer_id = 'cus-1'
    usuario.profile.save()
    monkeypatch.setattr(cartoes_salvos, '_mp', MPFalso({('POST', '/v1/customers/cus-1/cards'): (400, {'message': 'invalid token'})}))
    with pytest.raises(cartoes_salvos.CartaoNaoSalvo):
        cartoes_salvos.salvar(usuario, 'tok')


def test_listar_e_remover(usuario, monkeypatch):
    usuario.profile.mp_customer_id = 'cus-1'
    usuario.profile.save()
    mp = MPFalso({('GET', '/v1/customers/cus-1/cards'): (200, [CARTAO_MP])})
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)
    assert [c['final'] for c in cartoes_salvos.listar(usuario)] == ['6351']
    cartoes_salvos.remover(usuario, 'card-1')
    assert ('DELETE', '/v1/customers/cus-1/cards/card-1', None, None) in mp.chamadas


# ── API ──

def _cliente_logado(usuario):
    c = APIClient()
    c.force_authenticate(usuario)
    return c


def test_api_exige_login(loja_plataforma):
    r = APIClient().get(f'/api/v1/stores/{loja_plataforma.slug}/customer/cartoes/')
    assert r.status_code in (401, 403)


def test_api_lista_salva_e_remove(usuario, loja_plataforma, monkeypatch):
    usuario.profile.mp_customer_id = 'cus-1'
    usuario.profile.save()
    mp = MPFalso({
        ('GET', '/v1/customers/cus-1/cards'): (200, [CARTAO_MP]),
        ('POST', '/v1/customers/cus-1/cards'): (201, CARTAO_MP),
    })
    monkeypatch.setattr(cartoes_salvos, '_mp', mp)
    c = _cliente_logado(usuario)
    base = f'/api/v1/stores/{loja_plataforma.slug}/customer/cartoes/'

    r = c.get(base)
    assert r.status_code == 200
    assert r.json()['disponivel'] is True
    assert r.json()['cartoes'][0]['final'] == '6351'

    r = c.post(base, {'token': 'tok'}, format='json')
    assert r.status_code == 201
    assert r.json()['id'] == 'card-1'

    r = c.delete(base + 'card-1/')
    assert r.status_code == 204


def test_api_loja_com_conta_propria_nao_tem_carteira(usuario, db, monkeypatch):
    loja = make_store(usa_gateway_da_plataforma=False)
    monkeypatch.setattr(cartoes_salvos, '_mp', MPFalso())
    r = _cliente_logado(usuario).get(f'/api/v1/stores/{loja.slug}/customer/cartoes/')
    assert r.status_code == 200
    assert r.json() == {'disponivel': False, 'cartoes': []}


# ── Cobrança com cartão salvo ──

def test_pagador_leva_customer_id_do_cartao_salvo():
    from types import SimpleNamespace
    from apps.stores.services.mp_orders import build_payer
    pedido = SimpleNamespace(
        customer_name='Ana Souza', customer_email='a@exemplo.com', customer_phone='',
        order_number='X1', delivery_address={}, delivery_method='pickup',
    )
    payer = build_payer(pedido, 'a@exemplo.com', {'customer_id': 'cus-1'})
    assert payer['customer_id'] == 'cus-1'
    # 24/11: o MP recusa 'customer_id' junto com 'email' ("properties
    # combination not allowed") — com cartão salvo o pagador é só o cliente.
    assert payer == {'customer_id': 'cus-1'}
    assert 'customer_id' not in build_payer(pedido, 'a@exemplo.com', {})


def test_customer_do_cartao_vem_do_perfil_e_nunca_do_corpo(usuario, rf):
    from apps.stores.api.views.storefront_views import StoreCheckoutView
    usuario.profile.mp_customer_id = 'cus-dono'
    usuario.profile.save()

    def payload(user, corpo):
        req = rf.post('/x', data={}, content_type='application/json')
        req.user = user
        req.data = corpo
        return StoreCheckoutView()._build_payment_payload(req)

    forjado = {'payment': {'card_id': 'c1', '_mp_customer_id': 'cus-de-outro'}}
    assert payload(usuario, forjado)['_mp_customer_id'] == 'cus-dono'

    from django.contrib.auth.models import AnonymousUser
    assert '_mp_customer_id' not in payload(AnonymousUser(), forjado)
    assert '_mp_customer_id' not in payload(usuario, {'payment': {'_mp_customer_id': 'x'}})
