"""
O agente não pode inventar o que acompanha um produto.

Bug real (09/ago/2026): no WhatsApp do Pastita o atendente afirmou que o molho
vinha incluso na salada. Não vem — molho é vendido à parte. O modelo não mentiu
por mau prompt: nenhuma tool expunha composição, então ele preencheu a lacuna
com o que é estatisticamente comum.

Aqui a composição vira dado: variantes do produto e grupos do combo.
"""
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.agents.models import Agent
from apps.agents.services.langchain_service import LangchainService
from apps.stores.models import StoreCombo, ComboProductGroup, ComboProductGroupProductOption
from apps.stores.tests.factories import make_store, make_product, make_variant


def _tools(agent, store, phone=""):
    with patch.object(LangchainService, '_create_llm', return_value=Mock()), \
         patch.object(LangchainService, '_create_redis_client', return_value=Mock()):
        svc = LangchainService(agent)
    return {t.name: t for t in svc._build_tools(phone_number=phone, store=store)}


@pytest.fixture
def agent(db):
    return Agent.objects.create(
        name="Atendente",
        provider=Agent.AgentProvider.NVIDIA,
        system_prompt="Nunca prometa desconto.",
        context_prompt="",
    )


@pytest.fixture
def loja_com_salada_e_molho(db):
    store = make_store()
    salada = make_product(store, name="Salada Caesar", price=Decimal("28.00"))
    salada.description = "Alface americana, frango grelhado, croutons e parmesão."
    salada.save()
    molho = make_product(store, name="Molho", price=Decimal("4.00"))
    make_variant(molho, name="Caesar", price=Decimal("4.00"))
    make_variant(molho, name="Mostarda e Mel", price=Decimal("4.00"))
    return store, salada, molho


# ── detalhes_do_produto ──────────────────────────────────────────────────────

def test_produto_sem_composicao_diz_explicitamente_que_nada_acompanha(
    agent, loja_com_salada_e_molho
):
    """A ausência de acompanhamento tem que ser afirmada, não omitida.

    Silêncio é exatamente o que fez o modelo chutar "molho incluso".
    """
    store, salada, _ = loja_com_salada_e_molho
    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Caesar"})

    assert "Salada Caesar" in out
    assert "Não acompanha" in out
    assert "à parte" in out


def test_produto_com_variantes_lista_as_opcoes_e_o_preco(agent, loja_com_salada_e_molho):
    store, _, molho = loja_com_salada_e_molho
    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Molho"})

    assert "Caesar" in out
    assert "Mostarda e Mel" in out
    assert "4,00" in out or "4.00" in out


def test_produto_traz_descricao_inteira_sem_truncar(agent, loja_com_salada_e_molho):
    """buscar_produto cortava em 70 chars e engolia justamente a composição."""
    store, salada, _ = loja_com_salada_e_molho
    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Caesar"})

    assert salada.description in out
    assert "..." not in out.replace("…", "")


def test_produto_inexistente_nao_inventa(agent, loja_com_salada_e_molho):
    store, _, _ = loja_com_salada_e_molho
    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Feijoada"})

    assert "não encontrei" in out.lower() or "nenhum produto" in out.lower()


# ── detalhes_do_combo ────────────────────────────────────────────────────────

@pytest.fixture
def combo_com_molho_incluso(db, loja_com_salada_e_molho):
    """Kit onde o molho REALMENTE acompanha — o contra-exemplo do bug."""
    store, salada, molho = loja_com_salada_e_molho
    combo = StoreCombo.objects.create(
        store=store,
        name="Kit Família",
        slug="kit-familia",
        description="Duas saladas grandes com molho à escolha.",
        price=Decimal("60.00"),
        is_active=True,
    )
    g1 = ComboProductGroup.objects.create(
        combo=combo, title="Escolha 2 saladas",
        is_required=True, min_selections=2, max_selections=2, position=0,
    )
    ComboProductGroupProductOption.objects.create(group=g1, product=salada)
    g2 = ComboProductGroup.objects.create(
        combo=combo, title="Molho incluso",
        is_required=True, min_selections=1, max_selections=1, position=1,
    )
    ComboProductGroupProductOption.objects.create(group=g2, product=molho)
    return store, combo


def test_combo_lista_grupos_com_regra_de_escolha(agent, combo_com_molho_incluso):
    store, combo = combo_com_molho_incluso
    out = _tools(agent, store)['detalhes_do_combo'].invoke({"nome": "Kit Família"})

    assert "Kit Família" in out
    assert "Escolha 2 saladas" in out
    assert "Molho incluso" in out
    assert "Salada Caesar" in out
    assert "60,00" in out or "60.00" in out


def test_combo_marca_grupo_obrigatorio_e_quantidade(agent, combo_com_molho_incluso):
    store, combo = combo_com_molho_incluso
    out = _tools(agent, store)['detalhes_do_combo'].invoke({"nome": "Kit"})

    assert "2" in out
    assert "obrigat" in out.lower()


def test_combo_inexistente_nao_inventa(agent, combo_com_molho_incluso):
    store, _ = combo_com_molho_incluso
    out = _tools(agent, store)['detalhes_do_combo'].invoke({"nome": "Rodízio"})

    assert "não encontrei" in out.lower() or "nenhum combo" in out.lower()


def test_tools_novas_estao_registradas(agent, loja_com_salada_e_molho):
    store, _, _ = loja_com_salada_e_molho
    nomes = set(_tools(agent, store))

    assert {'detalhes_do_produto', 'detalhes_do_combo'} <= nomes
