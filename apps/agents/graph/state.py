"""
Estado do agente LangGraph.

Um único TypedDict viaja por todos os nós do grafo.
"""
from __future__ import annotations

from typing import Annotated, Any, List, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Histórico de mensagens — add_messages faz merge (não sobrescreve)
    messages: Annotated[list, add_messages]

    # Identidade da conversa (passado na invocação inicial)
    phone_number: str
    conversation_id: str
    session_id: str

    # Contexto carregado pelo nó load_context
    store: Optional[Any]       # instância Store do Django ORM (não serializável — só em memória)
    tools: List[Any]           # callables das tools, construídos com store/phone resolvidos
    customer_context: str      # texto formatado com histórico do cliente
    store_context: str         # texto formatado com info da loja + cardápio
    delivery_info: str         # texto formatado com taxa/condições de entrega
    knowledge_context: str     # exemplos aprendidos de atendimentos anteriores

    # Controle de loop
    tool_call_count: int       # iterações de tool-calling neste turno

    # Resposta final extraída pelo nó extract_response
    response: str
