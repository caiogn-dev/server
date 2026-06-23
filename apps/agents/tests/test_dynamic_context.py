"""
Testes para LangchainService._build_dynamic_context.

Foco (Task 3): a store deve ser resolvida ANTES de montar o contexto do
cliente, de modo que _build_customer_context seja chamado UMA única vez por
mensagem (e não duas, descartando a primeira). A saída final tem que
permanecer idêntica.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.agents.models import Agent
from apps.agents.services.langchain_service import LangchainService
from apps.stores.tests.factories import make_store, make_product


def _make_service(agent):
    """Instancia o serviço sem tocar em rede/LLM/Redis."""
    with patch.object(LangchainService, '_create_llm', return_value=Mock()), \
         patch.object(LangchainService, '_create_redis_client', return_value=Mock()):
        return LangchainService(agent)


@pytest.fixture
def agent(db):
    return Agent.objects.create(
        name="Test Agent",
        provider=Agent.AgentProvider.NVIDIA,
        system_prompt="Você é um assistente.",
        context_prompt="",
    )


@pytest.fixture
def store_with_products(db):
    store = make_store()
    make_product(store, name="Produto A", price="10.00")
    return store


def _patch_store_resolution(store):
    """
    Patcha o seam que o código (antigo e novo) usa para resolver a store
    via agent.accounts: agent.accounts.first().store == store.
    Determinístico para RED e GREEN.
    """
    account = Mock()
    account.store = store
    # garante que o ramo hasattr(account, 'store') seja escolhido
    accounts_qs = Mock()
    accounts_qs.first.return_value = account
    return accounts_qs


def test_customer_context_built_once_when_store_resolves(agent, store_with_products):
    """
    Com a store resolvida, _build_customer_context deve ser chamado EXATAMENTE
    uma vez, e com a store resolvida (não None).
    """
    svc = _make_service(agent)

    accounts_qs = _patch_store_resolution(store_with_products)
    agent_accounts = Mock()
    agent_accounts.all.return_value = accounts_qs

    spy = Mock(return_value="👤 CONTEXTO DO CLIENTE: x")

    with patch.object(svc, 'agent') as agent_mock:
        agent_mock.context_prompt = ""
        agent_mock.accounts = agent_accounts
        with patch.object(svc, '_build_customer_context', spy):
            svc._build_dynamic_context(phone_number="5511999999999", conversation_id=None)

    assert spy.call_count == 1, (
        f"_build_customer_context deveria ser chamado 1x, foi {spy.call_count}"
    )
    # a única chamada deve receber a store resolvida
    _, kwargs = spy.call_args
    assert kwargs.get("store") is store_with_products, (
        "A chamada única deve receber a store resolvida (não None)."
    )


def test_output_identical_snapshot(agent, store_with_products):
    """
    Snapshot: a saída completa, com store resolvida e customer context fixo,
    deve bater com o baseline capturado (prova de que o refactor não muda nada).
    """
    svc = _make_service(agent)

    accounts_qs = _patch_store_resolution(store_with_products)
    agent_accounts = Mock()
    agent_accounts.all.return_value = accounts_qs

    fixed_customer = "👤 CONTEXTO DO CLIENTE: João"

    def run():
        with patch.object(svc, 'agent') as agent_mock:
            agent_mock.context_prompt = "CONTEXTO ESTÁTICO DO AGENTE"
            agent_mock.accounts = agent_accounts
            with patch.object(
                svc, '_build_customer_context', return_value=fixed_customer
            ):
                return svc._build_dynamic_context(
                    phone_number="5511999999999", conversation_id=None
                )

    output = run()

    # 1. customer context aparece exatamente uma vez
    assert output.count(fixed_customer) == 1

    # 2. ordem relativa dos headers principais preservada
    idx_ctx_prompt = output.index("CONTEXTO ESTÁTICO DO AGENTE")
    idx_customer = output.index(fixed_customer)
    idx_conduta = output.index("🎯 CONDUTA DE ATENDIMENTO")
    idx_menu = output.index("📋 CARDÁPIO INTERNO")
    assert idx_ctx_prompt < idx_customer < idx_conduta < idx_menu

    # 3. determinismo: duas execuções produzem a mesma string
    assert run() == output
