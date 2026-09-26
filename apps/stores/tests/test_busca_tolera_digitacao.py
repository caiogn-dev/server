"""Casamento de produto tolera erro de digitação — com régua.

Medido em prod (30 d): 160 mensagens caíram em `unknown` e só 12 pedidos
saíram pelo WhatsApp. Uma parte é gente que escreveu o nome do produto torto:
"espesial file frango" não casava "Especial Filé de Frango" e virava "Como
posso te ajudar? 👇".

Régua (Levenshtein, sem lib nova):
- palavra com menos de 4 letras só casa exata — "mel" não pode virar "gel";
- até 1 letra de diferença; 2 quando as palavras têm 7 letras ou mais;
- palavra exata vale mais que aproximada: "molho" não empata com "Milho".
"""
import pytest

from apps.stores.models import StoreProduct
from apps.stores.services.busca_de_produto import candidatos_de_produto, distancia
from apps.stores.services.leitura_do_pedido import ler_pedido
from apps.stores.tests.factories import make_store


def _produtos(store, *nomes):
    for nome in nomes:
        StoreProduct.objects.create(
            store=store, name=nome, slug=nome.lower().replace(' ', '-'), price=10, is_active=True,
        )


@pytest.fixture
def loja(db):
    store = make_store(name='Cê Saladas Digitação')
    _produtos(store, 'Especial Filé de Frango', 'Frango em pedaços', 'Suco', 'Molho', 'Milho',
              'Mel de abelha')
    return store


def _nomes(store, texto):
    return [o.name for o in candidatos_de_produto(store, texto)]


def test_distancia_de_levenshtein():
    assert distancia('especial', 'espesial') == 1
    assert distancia('especie', 'especial') == 2
    assert distancia('frango', 'frango') == 0
    assert distancia('', 'abc') == 3


def test_nome_escrito_torto_casa_o_produto(loja):
    assert _nomes(loja, 'espesial file frango')[0] == 'Especial Filé de Frango'
    assert [(o.name, q) for o, q in ler_pedido(loja, 'quero um espesial file frango').itens] == [
        ('Especial Filé de Frango', 1),
    ]


def test_plural_continua_casando(loja):
    assert 'Suco' in _nomes(loja, 'sucos')


def test_palavra_curta_nao_usa_tolerancia(loja):
    assert _nomes(loja, 'gel') == []


def test_duas_letras_de_diferenca_so_em_palavra_longa(loja):
    # "especie" × "especial": 2 letras, as duas palavras com 7+ → casa.
    assert _nomes(loja, 'especie')[0] == 'Especial Filé de Frango'
    # "mooolho" × "molho": 2 letras, mas "molho" tem 5 → não casa.
    assert _nomes(loja, 'mooolho') == []


def test_exata_ganha_da_aproximada(loja):
    assert _nomes(loja, 'quero molho')[0] == 'Molho'
    assert [(o.name, q) for o, q in ler_pedido(loja, 'quero molho').itens] == [('Molho', 1)]


def test_salada_nao_casa_produto_de_outra_loja(loja, db):
    outra = make_store(name='Outra Loja')
    _produtos(outra, 'Saladas Tropicais')

    assert _nomes(loja, 'salada') == []
