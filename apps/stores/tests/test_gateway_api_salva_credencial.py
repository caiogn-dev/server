"""
A API do gateway precisa conseguir SALVAR a credencial.

`StorePaymentGatewaySerializer` declarava `access_token` em `extra_kwargs` como
write_only, mas `access_token` nunca esteve em `fields` — e `extra_kwargs` de
campo ausente é letra morta. Resultado: o endpoint que existe para o lojista
cadastrar a conta dele não gravava o token, e o checkout continuava caindo na
conta da plataforma.

E o inverso também importa: o token do lojista NUNCA pode voltar na leitura.
Quem abre a tela precisa saber se está configurado, não qual é o segredo.
"""
import pytest
from rest_framework.test import APIClient

from apps.stores.models import StorePaymentGateway
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(user=loja.owner)
    return c


def test_salva_o_access_token(api, loja):
    r = api.post('/api/v1/stores/payments/gateways/', {
        'store': str(loja.id),
        'name': 'Mercado Pago',
        'gateway_type': 'mercadopago',
        'access_token': 'APP_USR-DA-LOJA',
        'is_enabled': True,
        'is_sandbox': False,
    }, format='json')

    assert r.status_code == 201, r.data
    g = StorePaymentGateway.objects.get(store=loja)
    assert g.access_token == 'APP_USR-DA-LOJA'


def test_nunca_devolve_o_token_na_leitura(api, loja):
    StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type='mercadopago', access_token='SEGREDO',
    )

    r = api.get('/api/v1/stores/payments/gateways/', {'store': str(loja.id)})

    assert 'SEGREDO' not in str(r.data)


def test_leitura_diz_se_esta_configurado(api, loja):
    """A tela precisa distinguir "sem gateway" de "gateway sem token"."""
    StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type='mercadopago', access_token='SEGREDO',
    )

    r = api.get('/api/v1/stores/payments/gateways/', {'store': str(loja.id)})
    linhas = r.data['results'] if isinstance(r.data, dict) and 'results' in r.data else r.data

    assert linhas[0]['tem_credencial'] is True
    assert linhas[0]['connection_type'] == 'manual'


def test_editar_sem_mandar_token_nao_apaga_o_token(api, loja):
    """Trocar o nome não pode zerar a credencial e derrubar o checkout."""
    g = StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type='mercadopago', access_token='SEGREDO',
    )

    r = api.patch(f'/api/v1/stores/payments/gateways/{g.id}/', {'name': 'MP da Loja'}, format='json')

    assert r.status_code == 200, r.data
    g.refresh_from_db()
    assert g.access_token == 'SEGREDO'
