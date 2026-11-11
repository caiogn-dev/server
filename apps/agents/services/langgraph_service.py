"""
LangGraphService — substitui o agentic loop manual do LangchainService
"""
import logging
import time
from typing import Dict, Any, Optional

from ..models import Agent
from .langchain_service import LangchainService

from apps.agents.avisos import MENSAGEM_DE_ERRO_DO_LLM
from apps.agents.services.resposta_do_modelo import (
    RespostaDoModeloInvalida,
    texto_degenerado,
    texto_para_o_cliente,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LangGraphService — substitui o agentic loop manual do LangchainService
# ─────────────────────────────────────────────────────────────────────────────

class LangGraphService:
    """
    Agente baseado em LangGraph.

    Substitui o while-loop manual de tool calling do LangchainService por um
    StateGraph explícito.  Reutiliza _create_llm(), _build_tools() e
    _build_customer_context() do LangchainService — sem duplicar lógica.

    Interface idêntica a LangchainService.process_message() para troca
    transparente no webhook_service.
    """

    def __init__(self, agent: Agent):
        self.agent = agent
        self._lc = LangchainService(agent)   # reusa LLM + tools + contexto
        self._graph = None

    def _get_graph(self):
        """Compila o grafo uma vez e armazena em cache na instância."""
        if self._graph is None:
            from ..graph import build_agent_graph
            self._graph = build_agent_graph(self.agent, self._lc)
        return self._graph

    def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processa uma mensagem pelo grafo LangGraph.

        Carrega histórico do Redis antes de invocar e salva ao terminar,
        mantendo compatibilidade com a memória existente.
        """
        start = time.time()
        session_id = session_id or self._lc._generate_session_id()

        # ── Carrega histórico do Redis ─────────────────────────────────────
        from langchain_core.messages import HumanMessage as HM
        history_messages = []
        memory = self._lc._get_memory(session_id)
        if memory:
            try:
                history_messages = list(memory.messages[-self.agent.max_context_messages:])
            except Exception as exc:
                logger.warning("[LANGGRAPH] Falha ao carregar memória: %s", exc)
        # 11/nov/2026: lixo do modelo ficou gravado no Redis e voltava como
        # contexto, puxando o turno seguinte para o mesmo lixo.
        history_messages = [
            m for m in history_messages
            if not texto_degenerado(m.content if isinstance(m.content, str) else '')
        ]

        def _estado_inicial() -> dict:
            return {
                "messages": history_messages + [HM(content=message)],
                "phone_number": phone_number or "",
                "conversation_id": conversation_id or "",
                "session_id": session_id,
                "store": None,
                "tools": [],
                "customer_context": "",
                "store_context": "",
                "delivery_info": "",
                "response": "",
            }

        # ── Invoca o grafo ─────────────────────────────────────────────────
        try:
            response_text = ""
            for tentativa in (1, 2):
                final_state = self._get_graph().invoke(_estado_inicial())
                response_text = self._texto_aprovado(final_state.get("response", ""), start)
                if response_text:
                    break
                # Refazer repetiria criar_pedido/gerar_pix: pedido em dobro é
                # pior que cair no fallback.
                if final_state.get("tool_call_count"):
                    break
                if tentativa == 1:
                    logger.warning("[LANGGRAPH] Resposta vazia/inválida — refazendo uma vez")
        except Exception:
            logger.exception("[LANGGRAPH] Erro na execução do grafo")
            return {
                # Fonte única do aviso: reconhecer o texto é o que liga a
                # falha ao caminho do atendente (ver apps/agents/avisos.py).
                "response": MENSAGEM_DE_ERRO_DO_LLM,
                "session_id": session_id,
                "processing_time": time.time() - start,
                "model": self.agent.model_name,
                "tokens_used": 0,
                "order_created": None,
            }

        # ── Salva turno no Redis ───────────────────────────────────────────
        if memory and response_text:
            try:
                memory.add_user_message(message)
                memory.add_ai_message(response_text)
            except Exception as exc:
                logger.warning("[LANGGRAPH] Falha ao salvar memória: %s", exc)

        logger.info("[LANGGRAPH] Resposta: %r", response_text[:120])

        return {
            "response": response_text,
            "session_id": session_id,
            "processing_time": time.time() - start,
            "model": self.agent.model_name,
            "tokens_used": 0,
            "order_created": None,
        }

    def _texto_aprovado(self, texto: str, start: float) -> str:
        """O texto que pode ir ao cliente, ou '' se o modelo devolveu lixo.

        Mesma trava do loop antigo (`texto_para_o_cliente`): até 11/nov este
        caminho — o de produção — não passava por ela.
        """
        if not (texto or "").strip():
            return ""
        try:
            return texto_para_o_cliente(texto, None)
        except RespostaDoModeloInvalida as invalida:
            self._lc._registrar_resposta_barrada(invalida, None, start)
            return ""

    def get_conversation_history(self, session_id: str, limit: int = 50) -> list:
        return self._lc.get_conversation_history(session_id, limit)

    def clear_memory(self, session_id: str) -> bool:
        return self._lc.clear_memory(session_id)
