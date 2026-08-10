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


def test_produto_que_declara_o_que_inclui_nao_e_desmentido(agent, loja_com_salada_e_molho):
    """Caso real: SEXTA DO BACALHAU = 1 rondelli de bacalhau + 1 molho branco.

    É um produto único, não um combo. Sem lugar para declarar a composição, a
    tool afirmava "não acompanha nada" — e desmentia a própria loja.
    """
    store, _, _ = loja_com_salada_e_molho
    prato = make_product(store, name="Sexta do Bacalhau", price=Decimal("45.00"))
    prato.attributes = {"inclui": ["1 Rondelli de Bacalhau", "1 Molho Branco"]}
    prato.save()

    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Sexta"})

    assert "Acompanha" in out
    assert "1 Rondelli de Bacalhau" in out
    assert "1 Molho Branco" in out
    assert "Não acompanha nenhum item extra" not in out


def test_produto_que_declara_composicao_ainda_fecha_a_lista(agent, loja_com_salada_e_molho):
    """Declarar o que inclui não pode virar porta para o modelo somar extras."""
    store, _, _ = loja_com_salada_e_molho
    prato = make_product(store, name="Sexta do Bacalhau", price=Decimal("45.00"))
    prato.attributes = {"inclui": ["1 Rondelli de Bacalhau", "1 Molho Branco"]}
    prato.save()

    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Sexta"})

    assert "Nada além disso" in out


def test_inclui_vazio_volta_a_dizer_que_nada_acompanha(agent, loja_com_salada_e_molho):
    store, salada, _ = loja_com_salada_e_molho
    salada.attributes = {"inclui": []}
    salada.save()

    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Caesar"})

    assert "Não acompanha" in out


def test_inclui_malformado_nao_derruba_a_tool(agent, loja_com_salada_e_molho):
    """attributes é JSON livre — alguém vai salvar string em vez de lista."""
    store, salada, _ = loja_com_salada_e_molho
    salada.attributes = {"inclui": "molho branco"}
    salada.save()

    out = _tools(agent, store)['detalhes_do_produto'].invoke({"nome": "Caesar"})

    assert "molho branco" in out
    assert "Erro" not in out


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


def test_combo_declara_brinde_fixo(agent, combo_com_molho_incluso):
    """Caso real: 'na compra de 8 rondellis, ganhe 2 molhos' vivia só na
    descrição — a tool listava os grupos e parecia desmentir a promessa."""
    store, combo = combo_com_molho_incluso
    combo.metadata = {"inclui": ["2 molhos grátis"]}
    combo.save()

    out = _tools(agent, store)['detalhes_do_combo'].invoke({"nome": "Kit Família"})

    assert "2 molhos grátis" in out


def test_combo_inexistente_nao_inventa(agent, combo_com_molho_incluso):
    store, _ = combo_com_molho_incluso
    out = _tools(agent, store)['detalhes_do_combo'].invoke({"nome": "Rodízio"})

    assert "não encontrei" in out.lower() or "nenhum combo" in out.lower()


def test_tools_novas_estao_registradas(agent, loja_com_salada_e_molho):
    store, _, _ = loja_com_salada_e_molho
    nomes = set(_tools(agent, store))

    assert {'detalhes_do_produto', 'detalhes_do_combo'} <= nomes


# ── adicionar_combo_ao_carrinho ──────────────────────────────────────────────

def test_tool_de_combo_registrada(agent, combo_com_molho_incluso):
    store, _ = combo_com_molho_incluso
    assert 'adicionar_combo_ao_carrinho' in _tools(agent, store)


def test_combo_com_sabores_certos_entra_no_carrinho(agent, combo_com_molho_incluso, monkeypatch):
    """O caso real: o cliente fecha o combo e ele PRECISA existir no carrinho."""
    store, combo = combo_com_molho_incluso
    guardado = {}
    tools = _tools(agent, store, phone='5563999999999')

    import apps.agents.services.langchain_service as ls
    monkeypatch.setattr(ls.LangchainService, '_get_store_for_context', lambda self, **kw: store, raising=False)

    out = tools['adicionar_combo_ao_carrinho'].invoke(
        {"nome": "Kit Família", "sabores": "Salada Caesar, Salada Caesar"}
    )
    assert 'Erro' not in out


def test_sabor_inexistente_e_recusado_com_as_opcoes(agent, combo_com_molho_incluso):
    store, _ = combo_com_molho_incluso
    tools = _tools(agent, store, phone='5563999999999')

    out = tools['adicionar_combo_ao_carrinho'].invoke(
        {"nome": "Kit Família", "sabores": "Feijoada, Salada Caesar"}
    )

    assert 'Feijoada' in out
    assert 'Salada Caesar' in out


def test_quantidade_de_sabores_errada_e_recusada(agent, combo_com_molho_incluso):
    """Montar com menos escolhas do que o grupo exige entrega combo incompleto."""
    store, _ = combo_com_molho_incluso
    tools = _tools(agent, store, phone='5563999999999')

    out = tools['adicionar_combo_ao_carrinho'].invoke(
        {"nome": "Kit Família", "sabores": "Salada Caesar"}
    )

    assert 'precisa de' in out.lower()


def test_combo_inexistente_nao_inventa_na_adicao(agent, combo_com_molho_incluso):
    store, _ = combo_com_molho_incluso
    tools = _tools(agent, store, phone='5563999999999')

    out = tools['adicionar_combo_ao_carrinho'].invoke({"nome": "Rodizio", "sabores": "x"})

    assert 'não encontrado' in out.lower()
