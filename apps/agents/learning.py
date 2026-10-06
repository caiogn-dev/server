"""
Sistema de aprendizado do agente.

AgentLearningService extrai padrões de atendimentos anteriores e os
armazena em AgentKnowledgeEntry para injeção futura no contexto do LLM.

A abordagem é eficiente: analisa só as últimas N conversas, faz matching
por tópico com regras simples (sem embeddings), e usa o próprio LLM apenas
para gerar o exemplo de resposta — não para embeddings nem fine-tuning.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Regras de classificação de tópicos (sem LLM, sem embeddings)
# ─────────────────────────────────────────────────────────────────────────────

_TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("cardapio",    ["cardápio", "cardapio", "menu", "preço", "preco", "quanto custa", "valor",
                     "tem ", "vocês têm", "voces tem"]),
    ("entrega",     ["entrega", "frete", "taxa", "endereço", "bairro", "quanto fica",
                     "delivery", "motoboy", "prazo"]),
    ("pedido",      ["pedido", "pedir", "fazer pedido", "encomendar",
                     "meu pedido", "status do pedido", "onde está"]),
    ("pagamento",   ["pix", "pagamento", "pagar", "boleto", "cartão", "transferência",
                     "qr code", "código", "comprovante"]),
    ("saudacao",    ["oi", "olá", "boa tarde", "bom dia", "boa noite", "tudo bem",
                     "e aí", "salve", "mais informações", "mais informacoes",
                     "tenho interesse", "queria saber", "pode me ajudar"]),
    ("reclamacao",  ["reclamação", "problema", "errado", "não chegou", "frio",
                     "demora", "cancelar", "reembolso"]),
    ("indisponivel", ["esgotado", "acabou", "sem estoque", "não tem", "nao tem",
                      "indisponível"]),
]

# Inputs vagos — não guardar como exemplos de atendimento (sem produto/contexto específico)
_VAGUE_INPUT_PATTERNS = [
    r'^(oi|olá|ola|e aí|eai|bom dia|boa tarde|boa noite)[!?.\s]*$',
    r'^(quero\s+)?(mais\s+)?informa[çc][õo]es[!?.\s]*$',
    r'^(tenho interesse|pode me ajudar|queria saber)[!?.\s]*$',
    r'^\w{1,3}[!?.\s]*$',  # mensagem com 1-3 palavras apenas
]


def _texto_da_mensagem(conteudo) -> str:
    """Texto legível de uma mensagem, qualquer que seja o formato guardado.

    O campo `content` chega como texto puro, {"text": "..."},
    {"text": {"body": "..."}}, botão ({"body_text": ...}) ou mídia. O .strip()
    direto derrubava a tarefa inteira a cada 5 minutos.
    """
    if conteudo is None:
        return ""
    if isinstance(conteudo, str):
        return conteudo.strip()
    if isinstance(conteudo, dict):
        for chave in ("text", "body", "body_text", "caption"):
            valor = conteudo.get(chave)
            if isinstance(valor, dict):
                valor = valor.get("body") or valor.get("text")
            if isinstance(valor, str) and valor.strip():
                return valor.strip()
    return ""


def _classify_topic(text: str) -> str:
    text_lower = text.lower()
    for topic, keywords in _TOPIC_RULES:
        if any(kw in text_lower for kw in keywords):
            return topic
    return "outro"


# ─────────────────────────────────────────────────────────────────────────────
# Critérios de "boa resposta" (heurísticas simples)
# ─────────────────────────────────────────────────────────────────────────────

_BAD_RESPONSE_PATTERNS = [
    r"posso ajudar em mais alguma",
    r"nenhum produto encontrado",
    r"erro ao ",
    r"ferramenta .* não encontrada",
    r"desculpa, tive um probleminha",
    r"qualquer d[úu]vida estou aqui",
]

# Padrão de "dump": resposta que mistura taxa de entrega + categorias + produto — sinal de despejo
_DUMP_SIGNAL_PATTERNS = [
    r"taxa de entrega",
    r"categorias de produtos",
    r"r\$\s*\d+[,.]?\d*.*r\$\s*\d+[,.]?\d*.*r\$\s*\d+[,.]?\d*",  # 3+ preços na mesma resposta
]
_DUMP_SIGNAL_MIN_MATCHES = 2  # 2+ sinais = provável dump

_MIN_RESPONSE_TOKENS = 20   # respostas muito curtas provavelmente são echoes
_MAX_RESPONSE_TOKENS = 400  # respostas muito longas não são bons exemplos


def _is_good_response(response_text: str) -> bool:
    if not response_text:
        return False
    words = len(response_text.split())
    if words < _MIN_RESPONSE_TOKENS or words > _MAX_RESPONSE_TOKENS:
        return False
    for pattern in _BAD_RESPONSE_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            return False
    # Rejeita respostas que parecem "dump" de informações (vários sinais juntos)
    dump_hits = sum(
        1 for p in _DUMP_SIGNAL_PATTERNS
        if re.search(p, response_text, re.IGNORECASE)
    )
    if dump_hits >= _DUMP_SIGNAL_MIN_MATCHES:
        return False
    return True


# Quem mandou a mensagem (metadata.source). Só o bot ensina; atendente na
# conversa significa que o bot não resolveu sozinho.
_ORIGENS_DO_BOT = {"unified_llm", "unified_handler", "unified_template", "ai_agent"}
_ORIGENS_HUMANAS = {"whatsapp_inbox_page", "whatsapp_inbox_comando"}
_MAX_SUGESTOES_PENDENTES = 30

# O que envelhece (data, dia, hora, preço, promoção) ou tem cara de falha não
# pode virar exemplo: "hoje a promoção é o Camarão" estava no prompt semanas depois.
_ENVELHECE = re.compile(
    r"\b(hoje|ontem|amanh[aã]|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|semana|m[eê]s)\b"
    r"|\d{1,2}\s*[:h]\s*\d{2}|\b\d{1,2}/\d{1,2}\b|r\$\s*\d|\bpromo|\boferta|\bdesconto|\bcupom",
    re.IGNORECASE,
)
_PARECE_FALHA = re.compile(
    r"n[aã]o encontrei|n[aã]o consegui|desculp|\bops\b|😕|❌|⚠️|\berro\b", re.IGNORECASE,
)


def _envelhece_ou_falhou(texto: str, primeiro_nome: str = "") -> bool:
    if _ENVELHECE.search(texto) or _PARECE_FALHA.search(texto):
        return True
    return bool(primeiro_nome and len(primeiro_nome) >= 3 and re.search(rf"\b{re.escape(primeiro_nome)}\b", texto.lower()))


def models_Q(**kwargs):
    from django.db.models import Q
    return Q(**kwargs)


def _is_vague_input(text: str) -> bool:
    """Retorna True para inputs genéricos que não devem ser aprendidos como exemplos."""
    text = text.strip()
    if len(text.split()) <= 3:
        return True
    for pattern in _VAGUE_INPUT_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Serviço principal
# ─────────────────────────────────────────────────────────────────────────────

class AgentLearningService:
    """
    Analisa conversas recentes e extrai padrões para AgentKnowledgeEntry.

    Uso típico (Celery Beat, a cada 6h):
        AgentLearningService(agent).learn(lookback_hours=24)
    """

    def __init__(self, agent):
        self.agent = agent

    def learn(self, lookback_hours: int = 24, max_conversations: int = 100) -> dict:
        """Sugere exemplos tirados de conversas que VENDERAM sem mão humana.

        Até 06/10 aprendia de qualquer conversa e injetava no prompt na hora:
        conversa pessoal, resposta de erro e promoção de "hoje" viraram
        exemplo com confiança 1.0. Agora só sugere; o dono aprova no painel.
        """
        from apps.automation.models import CompanyProfile
        from apps.conversations.models import Conversation

        since = timezone.now() - timedelta(hours=lookback_hours)
        stats = {"analyzed": 0, "created": 0, "skipped": 0}

        perfis = (
            CompanyProfile.objects
            .filter(default_agent=self.agent, store__isnull=False)
            .select_related("store")
        )
        for perfil in perfis:
            loja = perfil.store
            if not loja.whatsapp_account_id:
                continue
            conversas = (
                Conversation.objects
                .filter(account_id=loja.whatsapp_account_id, last_customer_message_at__gte=since)
                .order_by("-last_customer_message_at")[:max_conversations]
            )
            for conv in conversas:
                stats["analyzed"] += 1
                criadas = self._aprender_da_conversa(conv, loja, since)
                stats["created"] += criadas
                if not criadas:
                    stats["skipped"] += 1

        logger.info("[LEARN] Agente %s — %s", self.agent.name, stats)
        return stats

    def _aprender_da_conversa(self, conversation, loja, since) -> int:
        """Quantas sugestões novas saíram desta conversa (0 quando ela não serve)."""
        from apps.handover.models import ConversationHandover
        from apps.stores.models import StoreOrder
        from apps.whatsapp.models import Message

        sufixo = "".join(c for c in str(conversation.phone_number or "") if c.isdigit())[-8:]
        if not sufixo:
            return 0
        vendeu = StoreOrder.objects.filter(
            store=loja, source="whatsapp", created_at__gte=since, customer_phone__endswith=sufixo,
        ).exclude(status__in=["cancelled", "refunded"]).exists()
        if not vendeu:
            return 0

        teve_atendente = ConversationHandover.objects.filter(conversation=conversation).filter(
            models_Q(created_at__gte=since) | models_Q(last_transfer_at__gte=since)
        ).exists()
        mensagens = list(
            Message.objects.filter(conversation=conversation, created_at__gte=since)
            .order_by("created_at")
            .values("direction", "text_body", "content", "metadata")
        )
        origens = [(m["metadata"] or {}).get("source") or "" for m in mensagens if m["direction"] == "outbound"]
        if teve_atendente or any(o in _ORIGENS_HUMANAS for o in origens):
            return 0

        nome = (conversation.contact_name or "").strip().split(" ")[0].lower()
        criadas = 0
        for atual, seguinte in zip(mensagens, mensagens[1:]):
            if atual["direction"] != "inbound" or seguinte["direction"] != "outbound":
                continue
            if ((seguinte["metadata"] or {}).get("source") or "") not in _ORIGENS_DO_BOT:
                continue
            pergunta = (atual["text_body"] or _texto_da_mensagem(atual["content"])).strip()
            resposta = (seguinte["text_body"] or _texto_da_mensagem(seguinte["content"])).strip()
            if not pergunta or _is_vague_input(pergunta) or not _is_good_response(resposta):
                continue
            if _envelhece_ou_falhou(resposta, nome) or _envelhece_ou_falhou(pergunta, nome):
                continue
            if self._sugerir(loja, pergunta, resposta):
                criadas += 1
        return criadas

    def _sugerir(self, loja, pergunta: str, resposta: str) -> bool:
        """Cria a sugestão desligada. False se a pergunta já existe (qualquer origem) ou a fila encheu."""
        from apps.agents.models import AgentKnowledgeEntry

        pergunta = pergunta[:300]
        ja_existe = AgentKnowledgeEntry.objects.filter(
            agent=self.agent, store=loja, example_input__iexact=pergunta,
        ).exists()
        if ja_existe:
            return False
        pendentes = AgentKnowledgeEntry.objects.filter(agent=self.agent, store=loja, source="sugestao").count()
        if pendentes >= _MAX_SUGESTOES_PENDENTES:
            return False
        AgentKnowledgeEntry.objects.create(
            agent=self.agent, store=loja, topic=_classify_topic(pergunta),
            example_input=pergunta, example_response=resposta[:500],
            source="sugestao", is_active=False, confidence=0.5,
            notes="Sugerido de uma conversa que virou pedido sem atendente.",
        )
        return True

    # ── API manual ────────────────────────────────────────────────────────────

    def add_manual_entry(
        self,
        topic: str,
        example_input: str,
        example_response: str,
        notes: str = "",
        store=None,
    ):
        """Adiciona ou atualiza entrada de conhecimento manualmente (via admin/API)."""
        from apps.agents.models import AgentKnowledgeEntry

        obj, created = AgentKnowledgeEntry.objects.update_or_create(
            agent=self.agent,
            store=store,
            topic=topic,
            example_input=example_input,
            defaults={
                "example_response": example_response,
                "notes": notes,
                "source": "manual",
                "confidence": 1.0,
                "is_active": True,
            },
        )
        return obj, created

    def decay_unused(self, days_inactive: int = 30) -> int:
        """Reduz confiança de entradas não usadas há muito tempo."""
        from apps.agents.models import AgentKnowledgeEntry

        cutoff = timezone.now() - timedelta(days=days_inactive)
        stale = AgentKnowledgeEntry.objects.filter(
            agent=self.agent,
            updated_at__lt=cutoff,
            confidence__gt=0.1,
        )
        count = stale.count()
        stale.update(confidence=models_F("confidence") * 0.9)
        return count


def models_F(field: str):
    from django.db.models import F
    return F(field)
