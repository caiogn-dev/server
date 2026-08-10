"""
Handler determinístico não pode atropelar uma conversa com o agente.

Incidente real (09/ago, 20:42): o agente perguntou qual molho o cliente queria
como cortesia do combo. O cliente respondeu "Branco". Em vez de chegar no
agente, a palavra bateu em `_message_matches_catalog_product`
(unified_service.py:283, regra `mensagem in nome_do_produto`):

    "branco" ⊂ "molho branco cremoso"  →  PRODUCT_MENTION  →  handler

…e o cliente recebeu um card de VENDA do Molho Branco por R$ 19,90 no meio de
um fluxo onde o molho era grátis. A resposta seguinte dele foi:

    "Não cara, o molho branco de cortesia do combo, vc acabou de perguntar isso"

A promoção para PRODUCT_MENTION é útil quando o cliente diz um nome de produto
do nada. Ela é destrutiva quando o agente acabou de fazer uma pergunta: aí a
mensagem é RESPOSTA, não menção.
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.automation.services.unified_service import LLMOrchestratorService
from apps.whatsapp.intents.detector import IntentType


@pytest.fixture
def loja_com_molho(db):
    from apps.stores.tests.factories import make_store, make_product
    store = make_store()
    make_product(store, name="Molho Branco Cremoso", price="19.90")
    return store


def _servico(store, com_agente):
    svc = LLMOrchestratorService.__new__(LLMOrchestratorService)
    svc.store = store
    svc.company = MagicMock()
    svc.company.use_ai_agent = com_agente
    svc.company.default_agent = MagicMock() if com_agente else None
    svc.agent = MagicMock() if com_agente else None
    svc.use_llm = com_agente
    return svc


def test_menciona_produto_sem_agente_continua_virando_product_mention(loja_com_molho):
    """Sem agente, o atalho determinístico é a única coisa que responde."""
    svc = _servico(loja_com_molho, com_agente=False)

    assert svc._message_matches_catalog_product('molho branco cremoso') is True


def test_resposta_curta_nao_e_promovida_quando_ha_agente(loja_com_molho):
    """"Branco" é resposta à pergunta do agente, não pedido de produto."""
    svc = _servico(loja_com_molho, com_agente=True)

    assert svc._message_matches_catalog_product('Branco') is False


def test_nome_completo_do_produto_ainda_vale_com_agente(loja_com_molho):
    """Quem escreve o nome inteiro está mesmo pedindo o produto."""
    svc = _servico(loja_com_molho, com_agente=True)

    assert svc._message_matches_catalog_product('Molho Branco Cremoso') is True


def test_fragmento_nao_vira_produto_com_agente(loja_com_molho):
    """Sem esta guarda, qualquer palavra do cardápio sequestra o turno."""
    svc = _servico(loja_com_molho, com_agente=True)

    assert svc._message_matches_catalog_product('cremoso') is False
