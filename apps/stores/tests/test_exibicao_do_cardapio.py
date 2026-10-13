"""Exibição do cardápio — o dono decide como o produto aparece na vitrine.

Pedido do dono (13/10), visto no Prefiro ("Definições → Cardápio e produtos"):
limite da descrição com "ver mais", foto à esquerda/direita, foto cortada ou
inteira, proporção padronizada, mostrar estoque baixo, esconder esgotados e o
texto do agradecimento. Regras:
- sem configuração, a vitrine recebe os padrões (nada muda para quem não mexeu);
- valor fora da lista ou fora do limite é recusado com mensagem clara;
- PATCH parcial só mexe no que veio, e não toca no resto do metadata;
- a vitrine recebe o bloco em /app-config/;
- loja alheia é 404.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.services.exibicao_do_cardapio import PADRAO

URL = '/api/v1/stores/exibicao-do-cardapio/'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-exib', password='x')
    return Store.objects.create(owner=dono, name='Cê Exib', slug='ce-exib', status='active',
                                metadata={'fiscal': {'cnpj': '1'}, 'informativos': []})


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


@pytest.mark.django_db
class TestPainel:
    def test_sem_configuracao_devolve_o_padrao(self, api, loja):
        r = api.get(f'{URL}?store={loja.slug}')
        assert r.status_code == 200, r.content
        assert r.json() == PADRAO

    def test_patch_parcial_grava_so_o_que_veio(self, api, loja):
        r = api.patch(f'{URL}?store={loja.slug}', {'descricao_limite': 120, 'foto_posicao': 'direita'}, format='json')
        assert r.status_code == 200, r.content
        corpo = r.json()
        assert corpo['descricao_limite'] == 120 and corpo['foto_posicao'] == 'direita'
        assert corpo['foto_encaixe'] == PADRAO['foto_encaixe']
        loja.refresh_from_db()
        assert loja.metadata['fiscal'] == {'cnpj': '1'}
        assert loja.metadata['informativos'] == []

    @pytest.mark.parametrize('campo,valor', [
        ('foto_posicao', 'em_cima_do_preco'),
        ('foto_encaixe', 'esticar'),
        ('foto_proporcao', '21:9'),
        ('logo_formato', 'estrela'),
        ('logo_alinhamento', 'direita'),
        ('descricao_limite', -1),
        ('descricao_limite', 5000),
        ('descricao_limite', 'muito'),
        ('mostrar_esgotados', 'talvez'),
        ('agradecimento_titulo', 'x' * 61),
        ('agradecimento_subtitulo', 'x' * 161),
    ])
    def test_valor_invalido_e_recusado(self, api, loja, campo, valor):
        r = api.patch(f'{URL}?store={loja.slug}', {campo: valor}, format='json')
        assert r.status_code == 400, r.content
        assert r.json()['error']

    def test_campo_desconhecido_e_ignorado(self, api, loja):
        r = api.patch(f'{URL}?store={loja.slug}', {'cor_do_ceu': 'azul'}, format='json')
        assert r.status_code == 200
        loja.refresh_from_db()
        assert 'cor_do_ceu' not in loja.metadata.get('exibicao', {})

    def test_loja_alheia_e_404(self, loja):
        outro = get_user_model().objects.create_user(username='intruso-exib', password='x')
        c = APIClient()
        c.force_authenticate(outro)
        assert c.get(f'{URL}?store={loja.slug}').status_code == 404
        assert c.patch(f'{URL}?store={loja.slug}', {'descricao_limite': 10}, format='json').status_code == 404


@pytest.mark.django_db
def test_vitrine_recebe_no_app_config(api, loja):
    api.patch(f'{URL}?store={loja.slug}', {'mostrar_esgotados': False, 'agradecimento_titulo': 'Valeu!'}, format='json')
    r = APIClient().get(f'/api/v1/stores/{loja.slug}/app-config/')
    assert r.status_code == 200, r.content
    exib = r.json()['exibicao']
    assert exib['mostrar_esgotados'] is False
    assert exib['agradecimento_titulo'] == 'Valeu!'
    assert exib['foto_encaixe'] == PADRAO['foto_encaixe']
