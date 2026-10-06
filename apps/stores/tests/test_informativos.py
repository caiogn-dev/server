"""Informativos — avisos da loja no cardápio, com começo e fim.

Pedido do dono (06/10), visto no Prefiro: "fechado no feriado", "novo horário",
"hoje sem entrega no Plano Diretor Sul". Regras:
- o cliente só recebe o que está NO AR agora (não o agendado, nem o encerrado,
  nem o pausado) e só os campos do aviso — nada do resto do metadata;
- fim antes do começo, aviso sem texto e texto gigante são recusados;
- gravar um informativo não mexe no resto do metadata da loja;
- loja alheia é 404.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store

URL = '/api/v1/stores/informativos/'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-inf', password='x')
    return Store.objects.create(owner=dono, name='Cê Inf', slug='ce-inf', status='active',
                                metadata={'fiscal': {'cnpj': '1'}, 'bot_fatos': [{'texto': 'x'}]})


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


def _criar(api, loja, **dados):
    corpo = {'titulo': 'Feriado', 'texto': 'Fechados no dia 12/10.', **dados}
    return api.post(f'{URL}?store={loja.slug}', corpo, format='json')


def _iso(**delta):
    return (timezone.now() + timedelta(**delta)).isoformat()


@pytest.mark.django_db
class TestPainel:
    def test_cria_e_lista_com_estado(self, api, loja):
        r = _criar(api, loja)
        assert r.status_code == 201, r.content
        [item] = api.get(f'{URL}?store={loja.slug}').json()
        assert item['titulo'] == 'Feriado' and item['estado'] == 'no_ar'

    def test_agendado_e_encerrado(self, api, loja):
        _criar(api, loja, titulo='Futuro', inicio=_iso(days=2))
        _criar(api, loja, titulo='Passado', inicio=_iso(days=-5), fim=_iso(days=-1))
        estados = {i['titulo']: i['estado'] for i in api.get(f'{URL}?store={loja.slug}').json()}
        assert estados == {'Futuro': 'agendado', 'Passado': 'encerrado'}

    def test_pausar_e_apagar(self, api, loja):
        criado = _criar(api, loja).json()
        r = api.patch(f"{URL}{criado['id']}/?store={loja.slug}", {'ativo': False}, format='json')
        assert r.json()['estado'] == 'pausado'
        assert api.delete(f"{URL}{criado['id']}/?store={loja.slug}").status_code == 204
        assert api.get(f'{URL}?store={loja.slug}').json() == []

    def test_nao_mexe_no_resto_do_metadata(self, api, loja):
        _criar(api, loja)
        loja.refresh_from_db()
        assert loja.metadata['fiscal'] == {'cnpj': '1'}
        assert loja.metadata['bot_fatos'] == [{'texto': 'x'}]

    @pytest.mark.parametrize('dados', [
        {'titulo': '', 'texto': ''},
        {'texto': 'x' * 281},
        {'inicio': _iso(days=3), 'fim': _iso(days=1)},
        {'fim': 'ontem de tarde'},
    ])
    def test_recusa_o_que_nao_faz_sentido(self, api, loja, dados):
        assert _criar(api, loja, **dados).status_code == 400

    def test_loja_alheia_e_404(self, loja):
        intruso = get_user_model().objects.create_user(username='intruso-inf', password='x')
        c = APIClient()
        c.force_authenticate(intruso)
        assert _criar(c, loja).status_code == 404


@pytest.mark.django_db
class TestVitrine:
    def test_app_config_so_traz_o_que_esta_no_ar(self, api, loja):
        _criar(api, loja, titulo='No ar')
        _criar(api, loja, titulo='Futuro', inicio=_iso(days=2))
        _criar(api, loja, titulo='Acabou', fim=_iso(minutes=-1))
        pausado = _criar(api, loja, titulo='Pausado').json()
        api.patch(f"{URL}{pausado['id']}/?store={loja.slug}", {'ativo': False}, format='json')

        r = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/')
        assert r.status_code == 200, r.content
        informativos = r.json()['informativos']
        assert [i['titulo'] for i in informativos] == ['No ar']
        assert set(informativos[0]) == {'id', 'titulo', 'texto'}
