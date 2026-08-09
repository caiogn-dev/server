"""
O prompt viaja inteiro em CADA ida ao LLM. Peso ali é latência multiplicada.

Medição em produção (09/ago, msg be0c7818): uma resposta levou 78,7s em 3
idas ao LLM (8s + 30s + 23s), estourou o timeout de 90s do orquestrador e foi
DESCARTADA — o cliente esperou ~3min por causa do reprocessamento.

Do bloco de cardápio do Pastita, 1128 de 2416 chars eram "Modo de preparo:
retire da embalagem, forno a 180°C..." — instrução de cozinha que não ajuda o
agente a decidir nada e era reenviada a cada rodada.
"""
from decimal import Decimal

import pytest

from apps.agents.graph import nodes
from apps.agents.graph.nodes import _catalog_summary
from apps.stores.tests.factories import make_store, make_product


@pytest.fixture
def loja_com_descricao_longa(db):
    store = make_store()
    p = make_product(store, name="Rondelli de Frango", price=Decimal("39.99"))
    p.description = (
        "Massa artesanal recheada com frango desfiado e queijo mussarela.\n\n"
        "Modo de preparo: Retire os rondellis da embalagem e disponha-os ainda "
        "congelados em um refratário. Cubra com o molho de sua preferência e leve "
        "ao forno preaquecido a 180°C por aproximadamente 30 minutos, ou "
        "micro-ondas em média 15 minutos. O tempo de preparo pode variar conforme "
        "a potência do forno."
    )
    p.save()
    return store, p


def test_cardapio_mantem_a_descricao_do_produto(loja_com_descricao_longa):
    store, _ = loja_com_descricao_longa
    resumo = _catalog_summary(store)

    assert "frango desfiado e queijo mussarela" in resumo


def test_cardapio_corta_o_modo_de_preparo(loja_com_descricao_longa):
    """Instrução de cozinha não decide venda e custa latência em toda rodada."""
    store, _ = loja_com_descricao_longa
    resumo = _catalog_summary(store)

    assert "Modo de preparo" not in resumo
    assert "180°C" not in resumo


def test_cardapio_limita_descricao_muito_longa(db):
    """Parágrafo único e gigante também não pode inflar o prompt."""
    store = make_store()
    p = make_product(store, name="Item Verboso", price=Decimal("10.00"))
    p.description = "palavra " * 200  # ~1600 chars num parágrafo só
    p.save()

    linha = [l for l in _catalog_summary(store).splitlines() if "Item Verboso" in l][0]

    assert len(linha) < 300


def test_limite_de_iteracoes_de_tool_e_baixo():
    """Cada iteração é uma ida ao LLM inteira. 6 rodadas = timeout garantido."""
    assert nodes._MAX_TOOL_ITERATIONS <= 3
