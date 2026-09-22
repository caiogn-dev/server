"""Link para página INTERNA da vitrine usa o endereço canônico.

Medido em 21/09: o convite de avaliação apontava para
`https://cesaladas.com.br/orders/<token>` — **404**. O mesmo caminho em
`https://cardapidex.com.br/ce-saladas/orders/<token>` responde 200.

O domínio próprio da loja serve a home e alguns caminhos (/perfil, /checkout,
/sucesso), mas não todos (/orders, /carteira, /promos dão 404). Como o convite
de avaliação leva para /orders, todo convite mandado apontava para o vazio —
81 avaliações, 2 com comentário.

Regra: a VITRINE (a home, o que a loja divulga) pode usar o domínio próprio; o
LINK INTERNO que o sistema manda usa o canônico, que serve tudo.
"""
import pytest

from apps.stores.services.links_da_vitrine import link_da_vitrine
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    loja = make_store(slug='loja-teste')
    loja.metadata = {'frontend_url': 'https://dominioproprio.com.br'}
    loja.save(update_fields=['metadata'])
    return loja


def test_ignora_o_dominio_proprio_da_loja(loja, settings):
    settings.STOREFRONT_BASE_URL = 'https://cardapidex.com.br'

    assert link_da_vitrine(loja, 'orders/abc') == 'https://cardapidex.com.br/loja-teste/orders/abc'


def test_barra_sobrando_nao_vira_barra_dupla(loja, settings):
    settings.STOREFRONT_BASE_URL = 'https://cardapidex.com.br/'

    assert link_da_vitrine(loja, '/orders/abc') == 'https://cardapidex.com.br/loja-teste/orders/abc'


def test_sem_caminho_devolve_a_vitrine_da_loja(loja, settings):
    settings.STOREFRONT_BASE_URL = 'https://cardapidex.com.br'

    assert link_da_vitrine(loja) == 'https://cardapidex.com.br/loja-teste'


@pytest.mark.django_db
def test_o_convite_de_avaliacao_usa_o_link_canonico():
    """Guarda: o convite voltar a usar o domínio próprio quebra tudo de novo."""
    from pathlib import Path

    fonte = Path('apps/whatsapp/intents/handlers/interactive.py').read_text()
    trecho = fonte[fonte.index('_handle_rating') if '_handle_rating' in fonte else 0:]
    assert 'link_da_vitrine' in trecho
    assert 'get_storefront_base_url' not in trecho
