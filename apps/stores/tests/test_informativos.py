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
        assert set(informativos[0]) == {
            'id', 'titulo', 'texto', 'formato', 'frequencia', 'imagem_url',
            'botao_texto', 'botao_link', 'versao',
        }



@pytest.mark.django_db
class TestModal:
    """Informativo vira modal: aparece ao entrar no cardápio e não repete para quem já viu."""

    def test_novo_nasce_modal_uma_vez(self, api, loja):
        item = _criar(api, loja).json()
        assert item['formato'] == 'modal'
        assert item['frequencia'] == 'uma_vez'

    def test_antigo_sem_formato_continua_faixa(self, loja):
        from apps.stores.services.informativos import no_ar_para_a_vitrine
        loja.metadata['informativos'] = [{'id': 'velho', 'titulo': 'Oi', 'texto': '', 'ativo': True}]
        loja.save()
        [item] = no_ar_para_a_vitrine(loja)
        assert item['formato'] == 'faixa'
        assert item['versao']

    def test_botao_so_com_link_seguro(self, api, loja):
        ok = _criar(api, loja, botao_texto='Ver combos', botao_link='/ce-saladas/promos')
        assert ok.status_code == 201, ok.content
        externo = _criar(api, loja, botao_texto='Insta', botao_link='https://instagram.com/x')
        assert externo.status_code == 201
        for ruim in ('javascript:alert(1)', '//evil.com', 'data:text/html,x'):
            assert _criar(api, loja, botao_texto='X', botao_link=ruim).status_code == 400

    def test_botao_sem_link_ou_link_sem_texto_e_recusado(self, api, loja):
        assert _criar(api, loja, botao_texto='Ver', botao_link='').status_code == 400
        assert _criar(api, loja, botao_texto='', botao_link='/x').status_code == 400

    def test_formato_e_frequencia_invalidos(self, api, loja):
        assert _criar(api, loja, formato='popup-gigante').status_code == 400
        assert _criar(api, loja, frequencia='sempre').status_code == 400

    def test_editar_muda_a_versao_para_mostrar_de_novo(self, api, loja):
        item = _criar(api, loja).json()
        editado = api.patch(f"{URL}{item['id']}/?store={loja.slug}", {'texto': 'Novo horário'},
                            format='json').json()
        assert editado['versao'] != item['versao']

    def test_sobe_imagem_e_vitrine_recebe(self, api, loja):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = io.BytesIO()
        Image.new('RGB', (20, 20), 'red').save(buf, 'PNG')
        item = _criar(api, loja).json()
        r = api.post(f"{URL}{item['id']}/imagem/?store={loja.slug}",
                     {'image': SimpleUploadedFile('a.png', buf.getvalue(), 'image/png')},
                     format='multipart')
        assert r.status_code == 200, r.content
        assert r.json()['imagem_url']
        vit = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/').json()['informativos']
        assert vit[0]['imagem_url']

    def test_imagem_que_nao_e_imagem_e_recusada(self, api, loja):
        from django.core.files.uploadedfile import SimpleUploadedFile
        item = _criar(api, loja).json()
        r = api.post(f"{URL}{item['id']}/imagem/?store={loja.slug}",
                     {'image': SimpleUploadedFile('a.png', b'<script>', 'image/png')},
                     format='multipart')
        assert r.status_code == 400
