"""Mensagem pronta para o entregador (22/10).

O dono mandava à mão no WhatsApp: cliente + telefone, endereço, CEP, link do
mapa — e, se for cobrar, quanto e como (maquininha, dinheiro e troco).
"""
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient

from apps.stores.models import Entregador, StoreOrder
from apps.stores.services.mensagem_do_entregador import texto_para_entregador
from apps.stores.tests.factories import make_store

pytestmark = pytest.mark.django_db

ENDERECO = {
    'street': 'Quadra 505 Sul, Alameda 18', 'number': '8', 'complement': '',
    'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO',
    'zip_code': '77016458', 'lat': -10.2, 'lng': -48.33,
}


@pytest.fixture
def loja():
    return make_store(name='Cê Saladas')


def _pedido(loja, **campos):
    dados = {
        'order_number': 'CE-2610227062', 'customer_name': 'ALINE NASCHE', 'customer_phone': '5511975373744',
        'total': Decimal('80.91'), 'subtotal': Decimal('70.91'), 'delivery_fee': Decimal('10'),
        'status': 'confirmed', 'payment_status': 'pending', 'delivery_method': 'delivery',
        'payment_method': 'card_on_delivery', 'delivery_address': ENDERECO,
        'delivery_lat': Decimal('-10.200000'), 'delivery_lng': Decimal('-48.330000'),
        **campos,
    }
    return StoreOrder.objects.create(store=loja, **dados)


def test_cliente_endereco_cep_e_mapa(loja):
    texto = texto_para_entregador(_pedido(loja))
    assert 'ALINE NASCHE - +55 (11) 97537-3744' in texto
    assert 'Quadra 505 Sul, Alameda 18' in texto
    assert '77016458' in texto
    assert 'https://www.google.com/maps/search/?api=1&query=-10.2%2C-48.33' in texto


def test_maquininha_diz_quanto_cobrar(loja):
    texto = texto_para_entregador(_pedido(loja))
    assert 'COBRAR R$ 80,91' in texto
    assert 'levar maquininha' in texto.lower()


def test_dinheiro_com_troco(loja):
    texto = texto_para_entregador(_pedido(loja, payment_method='cash', change_for=Decimal('100')))
    assert 'COBRAR R$ 80,91' in texto
    assert 'Dinheiro' in texto
    assert 'Troco para R$ 100,00' in texto
    assert 'levar R$ 19,09' in texto


def test_pago_nao_cobra(loja):
    texto = texto_para_entregador(_pedido(loja, payment_method='pix', payment_status='paid'))
    assert 'COBRAR' not in texto
    assert 'Pago' in texto


def test_sem_coordenada_usa_o_endereco_no_mapa(loja):
    texto = texto_para_entregador(_pedido(loja, delivery_lat=None, delivery_lng=None,
                                          delivery_address={**ENDERECO, 'lat': None, 'lng': None}))
    assert 'maps/search/?api=1&query=' in texto
    assert 'Palmas' in texto.split('query=')[1].replace('+', ' ').replace('%20', ' ')


def test_referencia_entra(loja):
    texto = texto_para_entregador(_pedido(loja, delivery_notes='Portão azul'))
    assert 'Ref: Portão azul' in texto


def test_api_devolve_texto_e_link_do_whatsapp_do_entregador(loja):
    joao = Entregador.objects.create(store=loja, nome='João', telefone='63 99999-0000')
    pedido = _pedido(loja, entregador=joao)
    api = APIClient()
    api.force_authenticate(user=loja.owner)
    r = api.get(f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/')
    assert r.status_code == 200, r.content
    corpo = r.json()
    assert 'COBRAR R$ 80,91' in corpo['texto']
    link = urlparse(corpo['whatsapp'])
    assert link.netloc == 'wa.me' and link.path == '/5563999990000'
    assert parse_qs(link.query)['text'][0] == corpo['texto']


def test_api_sem_entregador_abre_whatsapp_para_escolher_contato(loja):
    pedido = _pedido(loja)
    api = APIClient()
    api.force_authenticate(user=loja.owner)
    corpo = api.get(f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/').json()
    assert urlparse(corpo['whatsapp']).path == '/'


def test_api_outra_loja_nao_ve(loja):
    pedido = _pedido(loja)
    vizinha = make_store()
    api = APIClient()
    api.force_authenticate(user=vizinha.owner)
    assert api.get(f'/api/v1/stores/{loja.slug}/pedidos/{pedido.id}/entregador/').status_code in (403, 404)
