"""A tela monta a regra e pergunta ao servidor quantos são.

Duas coisas precisam vir do MESMO lugar: o catálogo de campos/operadores (para
a tela não inventar vocabulário) e a contagem (para o lojista ver o tamanho
antes de gastar envio).
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.tests.factories import make_store


@pytest.fixture
def dono(db):
    loja = make_store()
    return loja.owner, loja


def _cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_o_catalogo_de_campos_vem_do_servidor(dono):
    user, _ = dono

    r = _cliente(user).get('/api/v1/campaigns/audiencia/campos/')

    assert r.status_code == 200
    campos = {c['campo'] for c in r.data['campos']}
    assert {'pedidos', 'ticket_medio', 'ultima_compra', 'bairro', 'produto'} <= campos
    pedidos = next(c for c in r.data['campos'] if c['campo'] == 'pedidos')
    assert 'maior_que' in pedidos['operadores']


def test_previa_conta_e_explica_a_regra(dono):
    user, loja = dono

    r = _cliente(user).post('/api/v1/campaigns/audiencia/previa/', {
        'store_ids': [str(loja.id)],
        'regra': {'grupos': [{'condicoes': [
            {'campo': 'pedidos', 'operador': 'maior_que', 'valor': 3},
        ]}]},
    }, format='json')

    assert r.status_code == 200
    assert 'total' in r.data
    assert 'mais de 3 pedidos' in r.data['em_portugues']


def test_regra_vazia_nao_quebra(dono):
    user, loja = dono

    r = _cliente(user).post('/api/v1/campaigns/audiencia/previa/', {
        'store_ids': [str(loja.id)], 'regra': {},
    }, format='json')

    assert r.status_code == 200
    assert r.data['em_portugues'] == 'Todos os contatos'


def test_loja_de_outro_dono_nao_entra_na_conta(dono):
    user, _ = dono
    alheia = make_store()

    r = _cliente(user).post('/api/v1/campaigns/audiencia/previa/', {
        'store_ids': [str(alheia.id)], 'regra': {},
    }, format='json')

    # Sem acesso à loja pedida, a conta não pode usar os contatos dela.
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.data['total'] == 0
