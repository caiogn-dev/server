"""
Guardrails dos nós do grafo LangGraph — testes estáticos (sem DB, sem LLM real).

Cobre três camadas de proteção documentadas em nodes.py mas sem testes até aqui:

1. sondagem_node — intercepta primeiro contato vago sem chamar o LLM;
   o atendente não "despeja" cardápio, taxa ou preço para quem só disse "Oi".

2. should_skip_llm — roteador pós-sondagem: se sondagem já injetou AIMessage,
   pula o nó do LLM.

3. execute_tools_node: guardrail de busca com palavra de confirmação
   ("sim", "ok", etc.) — bloqueia buscar_produto para que o LLM não dispare
   uma busca de catálogo em resposta a "obrigada".

4. _delivery_summary — entrega só o que o cliente precisa saber (frete grátis,
   pedido mínimo); nunca expõe a lógica interna de cálculo de taxa.

5. Tool exception safety — exceção numa tool retorna mensagem segura,
   sem vazar host/porta/detalhe interno ao LLM.
"""
import re
import unittest
from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from apps.agents.graph.nodes import (
    _CONFIRMATION_WORDS,
    _delivery_summary,
    execute_tools_node,
    should_skip_llm,
    sondagem_node,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. sondagem_node
# ─────────────────────────────────────────────────────────────────────────────

class TestSondagemNode(unittest.TestCase):
    def _state(self, text):
        return {"messages": [HumanMessage(content=text)]}

    def test_saudacao_simples_recebe_sondagem(self):
        r = sondagem_node(self._state("Oi"))
        msgs = r.get("messages", [])
        self.assertTrue(msgs and isinstance(msgs[0], AIMessage))

    def test_bom_dia_recebe_sondagem(self):
        r = sondagem_node(self._state("Bom dia"))
        self.assertTrue(r.get("messages"))

    def test_boa_tarde_recebe_sondagem(self):
        r = sondagem_node(self._state("Boa tarde"))
        self.assertTrue(r.get("messages"))

    def test_quero_informacoes_recebe_sondagem(self):
        r = sondagem_node(self._state("Quero mais informações"))
        self.assertTrue(r.get("messages"))

    def test_oi_quero_mais_informacoes_recebe_sondagem(self):
        """Exemplo exato do system prompt — 'Oi quero mais informações'."""
        r = sondagem_node(self._state("Oi quero mais informações"))
        self.assertTrue(r.get("messages"))

    def test_quero_informacoes_sem_mais_recebe_sondagem(self):
        r = sondagem_node(self._state("Quero informações"))
        self.assertTrue(r.get("messages"))

    def test_tenho_interesse_recebe_sondagem(self):
        r = sondagem_node(self._state("Tenho interesse"))
        self.assertTrue(r.get("messages"))

    def test_pode_me_ajudar_recebe_sondagem(self):
        r = sondagem_node(self._state("Pode me ajudar"))
        self.assertTrue(r.get("messages"))

    def test_resposta_de_sondagem_e_uma_string_nao_vazia(self):
        r = sondagem_node(self._state("Oi"))
        content = r["messages"][0].content
        self.assertIsInstance(content, str)
        self.assertGreater(len(content), 10)

    def test_pedido_especifico_nao_interceptado(self):
        """'Quero uma salada' tem termo específico — vai para o LLM."""
        r = sondagem_node(self._state("Quero uma salada"))
        self.assertFalse(r.get("messages"))

    def test_oi_sobre_pagamento_nao_interceptado(self):
        """'Oi, sobre pagamento quero informações' é pergunta específica — vai para o LLM."""
        r = sondagem_node(self._state("Oi, sobre pagamento quero informações"))
        self.assertFalse(r.get("messages"))

    def test_pergunta_de_preco_nao_interceptada(self):
        r = sondagem_node(self._state("Qual o preço da salada?"))
        self.assertFalse(r.get("messages"))

    def test_pergunta_de_cardapio_nao_interceptada(self):
        r = sondagem_node(self._state("Quero ver o cardápio"))
        self.assertFalse(r.get("messages"))

    def test_pergunta_de_entrega_nao_interceptada(self):
        r = sondagem_node(self._state("Qual o frete?"))
        self.assertFalse(r.get("messages"))

    def test_segundo_turno_nao_interceptado(self):
        """Com mais de 1 mensagem no histórico, sondagem não atua."""
        state = {
            "messages": [
                HumanMessage(content="Oi"),
                AIMessage(content="Olá!"),
                HumanMessage(content="Oi"),
            ]
        }
        r = sondagem_node(state)
        self.assertFalse(r.get("messages"))

    def test_estado_sem_mensagens_nao_explode(self):
        r = sondagem_node({"messages": []})
        self.assertEqual(r, {})

    def test_estado_sem_campo_mensagens_nao_explode(self):
        r = sondagem_node({})
        self.assertEqual(r, {})


# ─────────────────────────────────────────────────────────────────────────────
# 2. should_skip_llm
# ─────────────────────────────────────────────────────────────────────────────

class TestShouldSkipLlm(unittest.TestCase):
    def test_ultimo_ai_message_retorna_skip(self):
        state = {"messages": [HumanMessage(content="Oi"), AIMessage(content="Olá!")]}
        self.assertEqual(should_skip_llm(state), "skip")

    def test_ultimo_human_message_retorna_agent(self):
        state = {"messages": [HumanMessage(content="Oi")]}
        self.assertEqual(should_skip_llm(state), "agent")

    def test_lista_vazia_retorna_agent_sem_explodir(self):
        self.assertEqual(should_skip_llm({"messages": []}), "agent")

    def test_sem_campo_mensagens_retorna_agent(self):
        self.assertEqual(should_skip_llm({}), "agent")


# ─────────────────────────────────────────────────────────────────────────────
# 3. execute_tools_node — guardrail de confirmação
# ─────────────────────────────────────────────────────────────────────────────

def _state_com_busca(arg, tool_name="buscar_produto"):
    """Monta state com um tool_call e uma tool espião que explode se chamada."""
    tc = {"id": "call_123", "name": tool_name, "args": {"nome": arg}}
    msg = AIMessage(content="", tool_calls=[tc])
    spy = Mock()
    spy.name = tool_name
    spy.invoke = Mock(side_effect=AssertionError("guardrail falhou: tool foi chamada"))
    return {"messages": [msg], "tools": [spy], "tool_call_count": 0}


class TestExecuteToolsGuardrail(unittest.TestCase):
    def test_sim_bloqueado_sem_chamar_tool(self):
        r = execute_tools_node(_state_com_busca("sim"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_ok_bloqueado(self):
        r = execute_tools_node(_state_com_busca("ok"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_obrigado_bloqueado(self):
        r = execute_tools_node(_state_com_busca("obrigado"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_tchau_bloqueado(self):
        r = execute_tools_node(_state_com_busca("tchau"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_todos_os_termos_de_confirmacao_bloqueados(self):
        for palavra in _CONFIRMATION_WORDS:
            with self.subTest(palavra=palavra):
                r = execute_tools_node(_state_com_busca(palavra))
                self.assertEqual(
                    r["messages"][0].content, "OK",
                    f"Palavra '{palavra}' não foi bloqueada pelo guardrail",
                )

    def test_arg_curto_nao_digito_bloqueado(self):
        """Arg de ≤ 3 chars não-dígito é ruído — bloqueado."""
        r = execute_tools_node(_state_com_busca("xx"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_arg_curto_un_bloqueado(self):
        r = execute_tools_node(_state_com_busca("un"))
        self.assertEqual(r["messages"][0].content, "OK")

    def test_numero_curto_nao_bloqueado(self):
        """'123' é dígito — pode ser código de produto; guardrail não bloqueia."""
        tc = {"id": "call_x", "name": "buscar_produto", "args": {"nome": "123"}}
        msg = AIMessage(content="", tool_calls=[tc])
        state = {"messages": [msg], "tools": [], "tool_call_count": 0}
        r = execute_tools_node(state)
        self.assertNotEqual(r["messages"][0].content, "OK")

    def test_produto_real_nao_bloqueado(self):
        """Busca legítima ('Caesar') passa direto para a tool."""
        tc = {"id": "call_y", "name": "buscar_produto", "args": {"nome": "Caesar"}}
        msg = AIMessage(content="", tool_calls=[tc])
        spy = Mock()
        spy.name = "buscar_produto"
        spy.invoke = Mock(return_value="Salada Caesar — R$ 28,00")
        state = {"messages": [msg], "tools": [spy], "tool_call_count": 0}
        r = execute_tools_node(state)
        spy.invoke.assert_called_once()
        self.assertIn("Caesar", r["messages"][0].content)

    def test_outra_tool_nao_bloqueada_por_confirmacao(self):
        """Palavras de confirmação não bloqueiam ver_carrinho."""
        tc = {"id": "call_z", "name": "ver_carrinho", "args": {}}
        msg = AIMessage(content="", tool_calls=[tc])
        spy = Mock()
        spy.name = "ver_carrinho"
        spy.invoke = Mock(return_value="Carrinho vazio.")
        state = {"messages": [msg], "tools": [spy], "tool_call_count": 0}
        r = execute_tools_node(state)
        spy.invoke.assert_called_once()

    def test_tool_exception_nao_vaza_detalhe_interno(self):
        """Exceção numa tool retorna mensagem segura — não vaza host/porta."""
        tc = {"id": "call_w", "name": "ver_carrinho", "args": {}}
        msg = AIMessage(content="", tool_calls=[tc])
        spy = Mock()
        spy.name = "ver_carrinho"
        spy.invoke = Mock(
            side_effect=Exception("DB connection failed at 127.0.0.1:5432 — timeout")
        )
        state = {"messages": [msg], "tools": [spy], "tool_call_count": 0}
        r = execute_tools_node(state)
        content = r["messages"][0].content
        self.assertNotIn("127.0.0.1", content)
        self.assertNotIn("5432", content)
        self.assertNotIn("DB connection", content)
        self.assertNotIn("timeout", content)

    def test_tool_exception_finalizar_pedido_retorna_mensagem_segura(self):
        tc = {"id": "call_v", "name": "finalizar_pedido", "args": {}}
        msg = AIMessage(content="", tool_calls=[tc])
        spy = Mock()
        spy.name = "finalizar_pedido"
        spy.invoke = Mock(side_effect=Exception("Pagamento: credenciais inválidas key=sk-123"))
        state = {"messages": [msg], "tools": [spy], "tool_call_count": 0}
        r = execute_tools_node(state)
        content = r["messages"][0].content
        self.assertNotIn("sk-123", content)
        self.assertNotIn("credenciais", content)

    def test_counter_incrementado(self):
        """tool_call_count cresce a cada execução (proteção anti-loop)."""
        tc = {"id": "call_c", "name": "ver_carrinho", "args": {}}
        msg = AIMessage(content="", tool_calls=[tc])
        spy = Mock()
        spy.name = "ver_carrinho"
        spy.invoke = Mock(return_value="Vazio.")
        state = {"messages": [msg], "tools": [spy], "tool_call_count": 1}
        r = execute_tools_node(state)
        self.assertEqual(r["tool_call_count"], 2)


# ─────────────────────────────────────────────────────────────────────────────
# 4. _delivery_summary — não expõe lógica interna
# ─────────────────────────────────────────────────────────────────────────────

def _loja(delivery_enabled=True, free_threshold=None, min_order=None):
    s = Mock()
    s.delivery_enabled = delivery_enabled
    s.free_delivery_threshold = free_threshold
    s.min_order_value = min_order
    return s


class TestDeliverySummary(unittest.TestCase):
    def test_entrega_desabilitada_diz_apenas_retirada(self):
        txt = _delivery_summary(_loja(delivery_enabled=False))
        self.assertIn("retirada", txt.lower())
        self.assertNotIn("taxa", txt.lower())

    def test_frete_gratis_exposto_se_configurado(self):
        txt = _delivery_summary(_loja(free_threshold=80))
        self.assertIn("80", txt)
        self.assertIn("grátis", txt.lower())

    def test_sem_threshold_nenhum_valor_de_taxa_hardcoded(self):
        """Sem frete grátis configurado, nenhum valor fixo de taxa no texto."""
        txt = _delivery_summary(_loja())
        self.assertFalse(re.search(r'\d+[.,]\d{2}', txt))

    def test_pede_endereco_para_calcular(self):
        """O agente deve pedir endereço/localização — não inventar taxa."""
        txt = _delivery_summary(_loja())
        self.assertTrue(
            "endere" in txt.lower() or "localiza" in txt.lower()
        )

    def test_pedido_minimo_exposto_se_configurado(self):
        txt = _delivery_summary(_loja(min_order=25))
        self.assertIn("25", txt)

    def test_texto_delivery_sem_regras_geograficas_internas(self):
        """
        O texto não pode conter variáveis internas do modelo de cálculo
        (bairros, coordenadas, faixas de distância).
        """
        txt = _delivery_summary(_loja())
        for proibido in ("latitude", "longitude", "bairro", "km", "raio"):
            self.assertNotIn(proibido, txt.lower(), msg=f"'{proibido}' viu no summary")


if __name__ == "__main__":
    unittest.main()
