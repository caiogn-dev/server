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
        """
        Ponto de entrada principal. Retorna estatísticas de o que foi aprendido.
        """
        from apps.conversations.models import Conversation

        since = timezone.now() - timedelta(hours=lookback_hours)

        # Busca conversas recentes ligadas a este agente
        conversations = (
            Conversation.objects
            .filter(
                agent_sessions__agent=self.agent,
                updated_at__gte=since,
            )
            .distinct()
            .order_by("-updated_at")[:max_conversations]
        )

        stats = {"analyzed": 0, "created": 0, "updated": 0, "skipped": 0}

        for conv in conversations:
            result = self._process_conversation(conv)
            stats["analyzed"] += 1
            stats[result] = stats.get(result, 0) + 1

        logger.info(
            "[LEARN] Agente %s — %s",
            self.agent.name,
            stats,
        )
        return stats

    def _process_conversation(self, conversation) -> str:
        """Extrai padrões de uma conversa. Retorna 'created', 'updated' ou 'skipped'."""
        from apps.whatsapp.models import WhatsAppMessage

        try:
            # Pega as mensagens da conversa (user + bot) em ordem
            messages = list(
                conversation.messages.order_by("created_at").values("role", "content")
            )
        except Exception:
            # fallback: tenta pegar via whatsapp messages
            try:
                messages = list(
                    WhatsAppMessage.objects
                    .filter(conversation=conversation)
                    .order_by("created_at")
                    .values("direction", "content")
                )
                messages = [
                    {"role": "user" if m["direction"] == "inbound" else "assistant",
                     "content": m["content"]}
                    for m in messages
                ]
            except Exception as exc:
                logger.debug("[LEARN] Sem mensagens para conversa %s: %s", conversation.id, exc)
                return "skipped"

        if len(messages) < 2:
            return "skipped"

        # Processa pares user→assistant
        created = updated = 0
        for i, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue
            # Próxima mensagem deve ser do assistente
            if i + 1 >= len(messages):
                continue
            next_msg = messages[i + 1]
            if next_msg.get("role") != "assistant":
                continue

            user_text = (msg.get("content") or "").strip()
            bot_text = (next_msg.get("content") or "").strip()

            if not user_text or _is_vague_input(user_text) or not _is_good_response(bot_text):
                continue

            topic = _classify_topic(user_text)

            # Resolve a loja da conversa para escopo correto
            store = self._resolve_store(conversation)

            result = self._upsert_knowledge(
                topic=topic,
                example_input=user_text[:300],
                example_response=bot_text[:500],
                store=store,
            )
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1

        if created:
            return "created"
        if updated:
            return "updated"
        return "skipped"

    def _resolve_store(self, conversation):
        """Tenta resolver a Store a partir da conversa."""
        try:
            from apps.automation.services.context_service import AutomationContextService
            ctx = AutomationContextService.resolve(conversation=conversation)
            return ctx.store
        except Exception:
            return None

    @transaction.atomic
    def _upsert_knowledge(
        self,
        topic: str,
        example_input: str,
        example_response: str,
        store=None,
    ) -> str:
        from apps.agents.models import AgentKnowledgeEntry

        # Verifica se já existe entrada similar (por input exato)
        existing = AgentKnowledgeEntry.objects.filter(
            agent=self.agent,
            store=store,
            topic=topic,
            example_input=example_input,
        ).first()

        if existing:
            # Atualiza confiança e contagem
            existing.usage_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.save(update_fields=["usage_count", "confidence", "updated_at"])
            return "updated"

        # Limita 20 entradas por tópico/store — remove a pior
        count = AgentKnowledgeEntry.objects.filter(
            agent=self.agent, store=store, topic=topic, is_active=True
        ).count()
        if count >= 20:
            worst = (
                AgentKnowledgeEntry.objects
                .filter(agent=self.agent, store=store, topic=topic, is_active=True)
                .order_by("confidence", "usage_count")
                .first()
            )
            if worst:
                worst.delete()

        AgentKnowledgeEntry.objects.create(
            agent=self.agent,
            store=store,
            topic=topic,
            example_input=example_input,
            example_response=example_response,
            source="auto",
            is_active=True,
        )
        return "created"

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
