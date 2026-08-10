"""
Nós do grafo LangGraph do atendente.

Cada função recebe AgentState e retorna um dict parcial
com os campos que quer atualizar no estado.
"""
from __future__ import annotations

import json
import logging
import re
import random
from typing import Any

from django.db import models
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .state import AgentState

logger = logging.getLogger(__name__)

_TOOL_CAPABLE_PROVIDERS = {"openai", "anthropic", "nvidia"}

# ─────────────────────────────────────────────────────────────────────────────
# NÓ 0: sondagem (intercepta primeiro contato vago — sem chamar LLM)
# ─────────────────────────────────────────────────────────────────────────────

_VAGUE_FIRST_CONTACT_PATTERNS = [
    r'^(oi|olá|ola|e\s*a[íi]|eae|bom dia|boa tarde|boa noite)[!?.\s,]*$',
    r'^(oi|olá|ola)[!?.\s,]*(tudo\s*(bem|bom|certo|ok)|como\s*vai)?[!?.\s,]*$',
    r'^(quero?\s+)?(mais\s+)?informa[çc][õo]es[!?.\s]*$',
    r'^(tenho interesse|pode me ajudar|me\s*ajuda|queria saber|vim saber)[!?.\s]*$',
    r'^(oi.{0,30})?(quero?\s+)?(mais\s+)?informa[çc][õo]es[!?.\s]*$',
]

_SPECIFIC_TERMS = [
    "cardápio", "cardapio", "menu", "pedir", "pedido", "quero ",
    "salada", "bebida", "entrega", "frete", "preço", "preco",
    "quanto", "disponível", "disponivel",
]

_SONDAGEM_RESPONSES = [
    "Oi! Que bom que entrou em contato 😊 O que você gostaria de saber — tem algum prato em mente, ou prefere dar uma olhada no cardápio?",
    "Olá! Com prazer em ajudar 😊 Está procurando algum prato específico, ou quer ver o que temos no cardápio?",
    "Oi! Fico feliz em te atender 😊 Tem algo específico que está buscando, ou quer dar uma olhada nas nossas opções?",
]


def sondagem_node(state: AgentState) -> dict:
    """
    Intercepta o primeiro contato vago e injeta uma AIMessage de sondagem
    sem chamar o LLM. Isso evita que modelos fracos "despejem" o cardápio.
    Só atua quando há 1 única mensagem no histórico (primeiro turno).
    """
    messages = state.get("messages") or []
    if len(messages) != 1:
        return {}

    last = messages[-1]
    text = (getattr(last, "content", "") or "").strip()

    word_count = len(text.split())
    is_vague = word_count <= 8 and any(
        re.match(p, text, re.IGNORECASE) for p in _VAGUE_FIRST_CONTACT_PATTERNS
    )
    has_specific = any(t in text.lower() for t in _SPECIFIC_TERMS)

    if is_vague and not has_specific:
        response = random.choice(_SONDAGEM_RESPONSES)
        logger.info("[SONDAGEM] Primeiro contato vago detectado — respondendo sem LLM")
        return {"messages": [AIMessage(content=response)]}

    return {}


def should_skip_llm(state: AgentState) -> str:
    """Se o nó de sondagem já injetou um AIMessage, pula direto para extract_response."""
    last = (state.get("messages") or [None])[-1]
    if isinstance(last, AIMessage):
        return "skip"
    return "agent"


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT  (o coração da personalidade humana do atendente)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
Você é {atendente_name}, atendente d{article} {store_name} no WhatsApp.{store_desc}

━━━━ COMO SE COMUNICAR ━━━━
• Fale de forma natural, como um atendente humano real — nunca robótico
• Respostas curtas para perguntas simples; detalhe só quando necessário
• Use o nome do cliente se souber ("Oi Ana!")
• Emojis só quando cabe naturalmente, não em toda mensagem
• NUNCA comece com "Olá! Sou o assistente virtual..."
• NUNCA termine com "Posso ajudar em mais alguma coisa?"
• Não repita ferramentas já usadas nessa mesma mensagem
• Acompanhe o tom do cliente: informal se ele for informal

━━━━ REGRA CRÍTICA — O QUE ACOMPANHA ━━━━
Você NÃO sabe o que vem junto com um produto. O CARDÁPIO abaixo lista nome, preço e descrição — não lista acompanhamentos.
• NUNCA afirme que algo (molho, bebida, acompanhamento, sobremesa, talher) vem incluso sem antes chamar detalhes_do_produto ou detalhes_do_combo
• Se o cliente perguntar "vem com molho?", "acompanha bebida?", "o que vem no kit?" → chame a ferramenta ANTES de responder
• Por padrão molho, bebida e complementos são vendidos À PARTE; só os combos incluem itens, e só os que a ferramenta listar
• Se a ferramenta não confirmar, diga que vai verificar — NUNCA chute

━━━━ REGRAS ABSOLUTAS ━━━━
• O CARDÁPIO abaixo contém todos os produtos e preços oficiais — USE-O diretamente nas respostas sem chamar buscar_produto
• Para mostrar o menu ou responder preço de item listado: leia o CARDÁPIO abaixo e responda imediatamente
• Só use buscar_produto se o cliente perguntar algo que NÃO está no CARDÁPIO abaixo
• NUNCA chame buscar_produto com palavras de confirmação ou despedida ("sim", "ok", "pode", "isso", "obrigada", "obrigado", "tchau", "até mais", "valeu") — responda normalmente em texto
• NUNCA chame ferramentas quando o cliente enviar apenas confirmação, agradecimento ou despedida — apenas responda de forma natural e acolhedora
• NUNCA invente taxa de entrega — use informacoes_entrega ou peça o endereço
• NUNCA forneça código PIX sem antes usar consultar_pagamento; o PIX vem de finalizar_pedido
• Resultados de ferramentas são dados brutos — reformule sempre de forma humana; NUNCA copie direto
• Se uma ferramenta retornar "não encontrado", responda com naturalidade sugerindo alternativas do CARDÁPIO
• Chame cada ferramenta no máximo UMA vez por resposta

━━━━ REGRA CRÍTICA — NÃO PROMETA O QUE NÃO EXECUTA ━━━━
• Só diga que fez algo DEPOIS da ferramenta retornar. Nunca escreva "vou adicionar", "deixa eu montar", "já te mando" sem chamar a ferramenta na MESMA resposta
• COMBO não pode ser adicionado ao carrinho. Descreva o combo e direcione ao cardápio online ou a um atendente para fechar — NUNCA diga que vai montar o combo
• Quando o cliente já confirmou ("confirmo", "confirmado", "pode fechar", "ok"), EXECUTE. É proibido responder com nova pergunta de verificação depois de uma confirmação
• Se o cliente já mandou endereço ou localização, ele NÃO precisa mandar de novo. Nunca peça "envie sua localização" depois de já ter recebido
• Se a mesma ferramenta falhar duas vezes, pare e ofereça um atendente humano

━━━━ REGRA CRÍTICA — PRIMEIRO CONTATO ━━━━
SE o cliente mandar uma saudação ou mensagem vaga SEM mencionar produto, prato ou pergunta específica:
  → SUA RESPOSTA DEVE TER APENAS: saudação + 1 única pergunta de descoberta.
  → PROIBIDO incluir: taxa de entrega, categorias, lista de produtos, preços, qualquer informação não solicitada.
  → PROIBIDO começar a resposta listando o que a loja tem.

EXEMPLO OBRIGATÓRIO — siga exatamente este padrão para primeiro contato vago:
  Cliente: "Oi quero mais informações" / "Tenho interesse" / "Oi, tudo bem?"
  Você: "Oi! Que bom que entrou em contato 😊 O que você gostaria de saber — tem algum prato em mente, ou prefere dar uma olhada no cardápio?"

NÃO FAÇA ISSO (proibido em resposta a mensagem vaga):
  "A taxa de entrega varia..." / "Temos as categorias..." / "O produto X custa R$..."

Só aprofunde um assunto (cardápio, entrega, produto) DEPOIS que o cliente perguntar sobre aquilo especificamente.

━━━━ CONVERSÃO ━━━━
• Apresente no máximo 2 opções de uma vez — nunca liste o cardápio inteiro na primeira resposta sobre produtos
• Descreva o produto com apelo sensorial: "fresco", "cremoso", "crocante" — não só nome e preço
• Use âncora social quando for verdade: "nosso mais pedido", "favorito da casa"
• Avance sempre com uma ação clara: "Posso incluir no seu pedido?" ou "Quer esse ou prefere ver mais opções?"
• Se o cliente hesitar, ofereça uma alternativa próxima — nunca finalize com frases passivas como "qualquer dúvida estou aqui"

━━━━ FLUXO DE PEDIDO (use nesta ordem) ━━━━
1. Cliente quer pedir → use adicionar_ao_carrinho(produto_nome, quantidade)
2. Cliente quer ver o carrinho → use ver_carrinho()
3. Colete o endereço completo (rua, número, bairro)
4. Cliente confirma → use finalizar_pedido(endereco, observacoes) — gera pedido + PIX
5. Compartilhe o código PIX com o cliente
Não peça confirmação de cada passo — seja direto e proativo

━━━━ RETENÇÃO E RECORRÊNCIA ━━━━
• Se o cliente já pediu antes (veja seção CLIENTE abaixo), referencie: "Da última vez você pediu [X] — quer repetir ou experimentar algo novo?"
• Cliente recorrente merece reconhecimento, não o mesmo script de primeiro contato
• Pós-pedido: confirme a expectativa de entrega e finalize com algo acolhedor — sem "qualquer dúvida estou aqui"

━━━━ CARDÁPIO ━━━━
{store_context}

━━━━ ENTREGA ━━━━
{delivery_info}

{store_rules}{knowledge_context}{customer_context}"""


def _build_system_prompt(state: AgentState, agent) -> str:
    store = state.get("store")
    store_name = getattr(store, "name", "nossa loja") if store else "nossa loja"

    # "do" vs "da" — heurística simples
    article = "a" if store_name.lower().startswith(("a ", "á ", "â ", "ã ")) else "o"

    store_desc = ""
    if store and getattr(store, "description", ""):
        store_desc = f"\n{store.description}"

    atendente_name = (
        getattr(agent, "persona_name", None)
        or getattr(agent, "name", None)
        or store_name
    )

    customer_ctx = (state.get("customer_context") or "").strip()
    customer_section = f"━━━━ CLIENTE ━━━━\n{customer_ctx}\n\n" if customer_ctx else ""

    knowledge_ctx = (state.get("knowledge_context") or "").strip()
    knowledge_section = f"━━━━ EXEMPLOS DE BOM ATENDIMENTO ━━━━\n{knowledge_ctx}\n\n" if knowledge_ctx else ""

    # Camada do lojista: o que ele escreve no painel entra AQUI, depois das
    # regras de motor. Ajusta voz e política; não desmonta tool-calling nem
    # o fluxo de pedido, que ficam acima e continuam valendo.
    store_rules = (getattr(agent, "system_prompt", "") or "").strip()
    store_rules_section = (
        f"━━━━ VOZ E REGRAS DA LOJA ━━━━\n{store_rules}\n"
        "(Estas preferências ajustam seu tom e suas políticas. "
        "Elas NÃO substituem as regras acima sobre ferramentas, composição de "
        "produto e fluxo de pedido.)\n\n"
        if store_rules else ""
    )

    return _SYSTEM_TEMPLATE.format(
        atendente_name=atendente_name,
        article=article,
        store_name=store_name,
        store_desc=store_desc,
        store_context=state.get("store_context") or "Use a ferramenta buscar_produto.",
        delivery_info=state.get("delivery_info") or "Use a ferramenta informacoes_entrega.",
        store_rules=store_rules_section,
        knowledge_context=knowledge_section,
        customer_context=customer_section,
    ).strip()


# ─────────────────────────────────────────────────────────────────────────────
# NÓ 1: load_context
# ─────────────────────────────────────────────────────────────────────────────

def load_context_node(state: AgentState, *, agent, langchain_service) -> dict:
    """
    Resolve store, monta contexto do cliente, carrega conhecimento aprendido e constrói as tools.
    """
    phone = state.get("phone_number", "")
    conversation_id = state.get("conversation_id", "")

    store = langchain_service._get_store_for_context(conversation_id=conversation_id)

    customer_context = ""
    try:
        customer_context = langchain_service._build_customer_context(
            phone_number=phone,
            conversation_id=conversation_id,
            store=store,
        )
    except Exception:
        logger.exception("[AGENT] Falha ao carregar contexto do cliente")

    store_context = ""
    delivery_info = ""
    if store:
        store_context = _catalog_summary(store)
        delivery_info = _delivery_summary(store)

    # Conhecimento aprendido de atendimentos anteriores
    knowledge_context = _load_knowledge_context(agent=agent, store=store)

    # Tools construídas com store+phone resolvidos — sem closures inválidos
    tools = langchain_service._build_tools(phone_number=phone, store=store)

    return {
        "store": store,
        "tools": tools,
        "customer_context": customer_context,
        "store_context": store_context,
        "delivery_info": delivery_info,
        "knowledge_context": knowledge_context,
        "tool_call_count": 0,
    }


_MAX_CATALOG_CHARS = 12000
_MAX_DESC_CHARS = 180


def _resumo_da_descricao(texto: str) -> str:
    """Primeiro parágrafo da descrição, curto.

    O cardápio inteiro viaja em CADA ida ao LLM, então cada caractere aqui é
    latência multiplicada pelo número de rodadas de tool. "Modo de preparo:
    forno a 180°C por 30 minutos" não ajuda o agente a vender e representava
    quase metade do bloco. A descrição completa continua disponível sob
    demanda em detalhes_do_produto.
    """
    primeiro = (texto or "").strip().split("\n\n")[0].strip()
    # Alguns cadastros não separam por parágrafo — cortar no marcador também.
    for marcador in ("Modo de preparo", "Modo de Preparo", "MODO DE PREPARO"):
        if marcador in primeiro:
            primeiro = primeiro.split(marcador)[0].strip()
    primeiro = " ".join(primeiro.split())
    if len(primeiro) > _MAX_DESC_CHARS:
        primeiro = primeiro[:_MAX_DESC_CHARS].rsplit(" ", 1)[0] + "…"
    return primeiro


def _catalog_summary(store) -> str:
    try:
        from apps.stores.models import StoreCategory, StoreProduct
        cats = (
            StoreCategory.objects
            .filter(store=store, is_active=True)
            .exclude(name__icontains="ingrediente")
            .order_by("sort_order")[:8]
        )
        # Sem corte por quantidade: cortar em 12 fazia sumir metade do cardápio
        # de loja real, e o modelo então "completava" o que faltava chutando.
        # _MAX_CATALOG_CHARS protege a janela de contexto sem esconder itens
        # silenciosamente — quando corta, avisa.
        products = (
            StoreProduct.objects
            .filter(store=store, is_active=True, status="active")
            .exclude(tags__contains=["ingrediente"])
            .order_by("sort_order")
            .select_related("category")
        )
        lines = []
        if cats:
            lines.append("Categorias: " + ", ".join(c.name for c in cats))
        if products:
            lines.append("Itens:")
            for p in products:
                cat = f"[{p.category.name}] " if p.category else ""
                desc = f" — {_resumo_da_descricao(p.description)}" if getattr(p, "description", "") else ""
                lines.append(f"  • {cat}{p.name} — R$ {p.price}{desc}")

        # Combos eram invisíveis: o agente não sabia que "Sexta do Bacalhau"
        # existia, muito menos o que vinha dentro.
        from apps.stores.models import StoreCombo
        combos = StoreCombo.objects.filter(store=store, is_active=True).order_by("sort_order")
        if combos:
            lines.append("Combos (use detalhes_do_combo para saber o que vem dentro):")
            for c in combos:
                lines.append(f"  • {c.name} — R$ {c.price}")

        texto = "\n".join(lines) if lines else "Use buscar_produto para detalhes."
        if len(texto) > _MAX_CATALOG_CHARS:
            texto = (
                texto[:_MAX_CATALOG_CHARS]
                + "\n(cardápio truncado — use buscar_produto ou detalhes_do_produto "
                  "para os itens não listados acima)"
            )
        return texto
    except Exception as exc:
        logger.warning("[AGENT] Erro ao montar cardápio: %s", exc)
        return ""


def _load_knowledge_context(agent, store) -> str:
    """Carrega exemplos aprendidos de atendimentos anteriores para injetar no prompt."""
    try:
        from apps.agents.models import AgentKnowledgeEntry
        entries = (
            AgentKnowledgeEntry.objects
            .filter(agent=agent, is_active=True)
            .filter(
                models.Q(store=store) | models.Q(store__isnull=True)
            )
            .order_by("-confidence", "-usage_count")[:5]
        )
        if not entries:
            return ""
        lines = []
        for e in entries:
            lines.append(f"[{e.topic}] Cliente: \"{e.example_input}\" → Você: \"{e.example_response}\"")
            if e.notes:
                lines.append(f"  Nota: {e.notes}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("[AGENT] Sem knowledge entries: %s", exc)
        return ""


def _delivery_summary(store) -> str:
    if not getattr(store, "delivery_enabled", True):
        return "Não fazemos entregas. Apenas retirada no local."
    parts = ["Taxa varia conforme o endereço (peça localização para calcular)."]
    if getattr(store, "free_delivery_threshold", None):
        parts.append(f"Frete grátis acima de R$ {store.free_delivery_threshold}.")
    if getattr(store, "min_order_value", None):
        parts.append(f"Pedido mínimo: R$ {store.min_order_value}.")
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# NÓ 2: agent (LLM call com tools bound dinamicamente)
# ─────────────────────────────────────────────────────────────────────────────

def agent_node(state: AgentState, *, agent, langchain_service) -> dict:
    """
    Chama o LLM. Se a resposta tiver tool_calls, o roteador vai para execute_tools.
    Caso contrário, é a resposta final.
    """
    tools = state.get("tools") or []
    llm = langchain_service.llm

    use_tools = (
        bool(tools)
        and agent.provider.lower() in _TOOL_CAPABLE_PROVIDERS
    )
    llm_bound = llm.bind_tools(tools) if use_tools else llm

    system_prompt = _build_system_prompt(state, agent)
    messages = [SystemMessage(content=system_prompt)] + list(state["messages"])

    try:
        response: AIMessage = llm_bound.invoke(messages)
    except Exception:
        logger.exception("[AGENT] Erro ao invocar LLM")
        response = AIMessage(content="Desculpa, tive um probleminha aqui. Pode repetir?")

    return {"messages": [response]}


# ─────────────────────────────────────────────────────────────────────────────
# NÓ 3: execute_tools (loop de tool calling — ativado pelo roteador)
# ─────────────────────────────────────────────────────────────────────────────

# Cada iteração é uma ida completa ao LLM, com o prompt inteiro de volta na
# rede. Em produção, 3 rodadas deram 78s e estouraram o timeout de 90s do
# orquestrador. Duas rodadas cobrem "pergunta → consulta → responde", que é o
# padrão real; a terceira quase sempre era o modelo repetindo ferramenta.
_MAX_TOOL_ITERATIONS = 2


_CONFIRMATION_WORDS = frozenset({
    'sim', 'ok', 'okay', 'pode', 'isso', 'certo', 'claro', 'confirmado',
    'obrigada', 'obrigado', 'valeu', 'vlw', 'tchau', 'ate mais', 'até mais',
    'flw', 'falou', 'ótimo', 'otimo', 'perfeito', 'combinado', 'entendido',
})

_USER_SAFE_TOOL_ERRORS: dict = {
    'buscar_produto': 'Não encontrei esse produto no momento.',
    'detalhes_do_produto': 'Não consegui confirmar a composição desse item agora — vou verificar.',
    'detalhes_do_combo': 'Não consegui confirmar o que vem nesse combo agora — vou verificar.',
    'adicionar_ao_carrinho': 'Não consegui adicionar ao carrinho agora.',
    'ver_carrinho': 'Não consegui acessar seu carrinho agora.',
    'finalizar_pedido': 'Não consegui finalizar o pedido agora. Tente novamente.',
    'salvar_endereco_entrega': 'Não consegui salvar o endereço. Pode me passar novamente?',
    'consultar_pagamento': 'Não consegui consultar o pagamento agora.',
    'informacoes_entrega': 'Não consegui carregar as informações de entrega.',
    'listar_cardapio': 'Não consegui carregar o cardápio agora.',
}


def execute_tools_node(state: AgentState) -> dict:
    """
    Executa os tool_calls do último AIMessage e injeta ToolMessages no estado.
    Limite de iterações para evitar loops infinitos.
    """
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not getattr(last, "tool_calls", None):
        return {}

    tool_map = {t.name: t for t in (state.get("tools") or [])}
    results = []

    for tc in last.tool_calls:
        # Guardrail: never call buscar_produto with a confirmation/farewell word
        if tc["name"] == "buscar_produto":
            arg = (tc["args"].get("nome") or tc["args"].get("query") or "").strip().lower()
            if arg in _CONFIRMATION_WORDS or (len(arg) <= 3 and not arg.isdigit()):
                logger.warning("[AGENT TOOL] buscar_produto bloqueado com arg inválido: %r", arg)
                results.append(ToolMessage(content="OK", tool_call_id=tc["id"]))
                continue

        fn = tool_map.get(tc["name"])
        try:
            result = fn.invoke(tc["args"]) if fn else f"Ferramenta '{tc['name']}' não encontrada."
        except Exception as exc:
            logger.exception("[AGENT TOOL] %s falhou", tc["name"])
            result = _USER_SAFE_TOOL_ERRORS.get(tc["name"], "Não consegui completar essa ação agora.")
        logger.info("[AGENT TOOL] %s → %s", tc["name"], str(result)[:120])
        results.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    current_count = state.get("tool_call_count") or 0
    return {"messages": results, "tool_call_count": current_count + 1}


# ─────────────────────────────────────────────────────────────────────────────
# ROTEADOR
# ─────────────────────────────────────────────────────────────────────────────

def should_use_tools(state: AgentState) -> str:
    # Hard stop after max iterations to avoid infinite loops
    if (state.get("tool_call_count") or 0) >= _MAX_TOOL_ITERATIONS:
        logger.warning("[AGENT] Limite de iterações atingido — forçando extração de resposta")
        return "end"
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "call_tools"
    return "end"


# ─────────────────────────────────────────────────────────────────────────────
# NÓ 4: extract_response
# ─────────────────────────────────────────────────────────────────────────────

def extract_response_node(state: AgentState) -> dict:
    """Extrai o texto final do último AIMessage."""
    last = state["messages"][-1]
    content = ""
    if isinstance(last, AIMessage):
        raw = last.content
        if isinstance(raw, str):
            content = raw
        elif isinstance(raw, list):
            # Anthropic retorna lista de blocos de conteúdo
            for block in raw:
                if isinstance(block, dict) and block.get("type") == "text":
                    content += block.get("text", "")
                elif isinstance(block, str):
                    content += block
        else:
            content = json.dumps(raw, ensure_ascii=False)
    return {"response": content.strip()}
