"""
Grafo LangGraph do atendente.

build_agent_graph(agent, langchain_service) retorna um CompiledGraph.

Fluxo:
  load_context → agent → [roteador] → execute_tools → agent (loop)
                                   → extract_response → END
"""
from __future__ import annotations

import functools
import logging

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    load_context_node,
    agent_node,
    execute_tools_node,
    extract_response_node,
    should_use_tools,
)

logger = logging.getLogger(__name__)


def build_agent_graph(agent, langchain_service):
    """
    Monta e compila o StateGraph do atendente.

    Parâmetros
    ----------
    agent : apps.agents.models.Agent
    langchain_service : LangchainService
        Instância reutilizada para LLM, tools e contexto — sem duplicar código.
    """
    _load_ctx = functools.partial(
        load_context_node,
        agent=agent,
        langchain_service=langchain_service,
    )
    _agent = functools.partial(
        agent_node,
        agent=agent,
        langchain_service=langchain_service,
    )

    g = StateGraph(AgentState)
    g.add_node("load_context", _load_ctx)
    g.add_node("agent", _agent)
    g.add_node("execute_tools", execute_tools_node)
    g.add_node("extract_response", extract_response_node)

    g.set_entry_point("load_context")
    g.add_edge("load_context", "agent")
    g.add_edge("execute_tools", "agent")   # após tools, volta ao LLM
    g.add_edge("extract_response", END)

    g.add_conditional_edges(
        "agent",
        should_use_tools,
        {"call_tools": "execute_tools", "end": "extract_response"},
    )

    return g.compile()
