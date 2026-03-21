#!/usr/bin/env python
"""
MCP Server — WhatsApp Bot Pipeline Inspector
============================================

Fornece ao Claude Code (e a qualquer cliente MCP) visibilidade completa do
pipeline de automação WhatsApp: intents, handlers, agentes LLM, templates,
sessões, health e debug de mensagens em tempo real.

Ferramentas disponíveis:
  pipeline_overview        — arquitetura completa do pipeline
  pipeline_health          — health check de todos os subsistemas
  pipeline_stats           — métricas das últimas N horas
  list_intent_patterns     — todos os intents e seus regex patterns
  list_handlers            — mapa intent → handler class
  list_automessages        — AutoMessages configurados no banco (por loja)
  list_agents              — agentes LLM cadastrados
  get_company_profile      — configuração de automação de uma loja
  get_store_context        — contexto resolvido para uma conta WhatsApp
  debug_message            — simula o processamento de uma mensagem
  detect_intent            — roda só a detecção de intent em um texto
  get_session              — sessão ativa de um número de telefone
  trace_conversation       — últimas mensagens de uma conversa
  list_active_sessions     — sessões ativas com carrinho / pagamento pendente
  list_flows               — fluxos de bot configurados (AgentFlow)
  check_store_products     — produtos ativos de uma loja (para validar cardápio)

Instalação (uma vez):
  pip install mcp

Rodar o servidor:
  python mcp_whatsapp_bot.py

Registrar no Claude Code:
  claude mcp add whatsapp-bot -- python /caminho/para/mcp_whatsapp_bot.py

Variáveis de ambiente necessárias (mesmas do Django):
  DJANGO_SETTINGS_MODULE   (padrão: config.settings.production)
  DATABASE_URL
  REDIS_URL
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from typing import Any, Dict, List, Optional

# ─── Bootstrap Django antes de importar qualquer model ───────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

# Adiciona o diretório do projeto ao sys.path
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import django
django.setup()

# ─── Agora podemos importar o SDK MCP e os models Django ─────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server('whatsapp-bot-pipeline')

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _j(data: Any) -> str:
    """Serializa para JSON indentado."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type='text', text=_j(data))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type='text', text=json.dumps({'error': msg}, ensure_ascii=False))]


# ══════════════════════════════════════════════════════════════════════════════
#  DEFINIÇÃO DAS FERRAMENTAS
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name='pipeline_overview',
            description=textwrap.dedent("""\
                Retorna a arquitetura completa do pipeline de automação WhatsApp.
                Explica cada etapa, o que faz, quais modelos usa e onde pode falhar.
                Ideal para entender o sistema antes de debugar.
            """),
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='pipeline_health',
            description=textwrap.dedent("""\
                Health check completo: banco de dados, Redis/cache, Celery workers,
                agentes LLM, backlog de mensagens agendadas e sessões obsoletas.
                Retorna status: ok | degraded | down com detalhes de cada subsistema.
            """),
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='pipeline_stats',
            description='Métricas do pipeline nas últimas N horas (source, intents, drops, timeouts).',
            inputSchema={
                'type': 'object',
                'properties': {
                    'hours': {'type': 'integer', 'default': 24, 'description': 'Janela de tempo em horas'},
                },
                'required': [],
            },
        ),
        Tool(
            name='list_intent_patterns',
            description=textwrap.dedent("""\
                Lista todos os IntentTypes com seus regex patterns de detecção.
                Útil para entender por que um intent específico está ou não sendo detectado.
                Inclui mapeamento intent → evento AutoMessage.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'filter_intent': {'type': 'string', 'description': 'Filtrar por nome de intent (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='list_handlers',
            description=textwrap.dedent("""\
                Lista todos os IntentHandlers mapeados no HANDLER_MAP.
                Para cada handler: qual intent atende, o que faz, se usa self.store,
                se gera resposta interativa ou texto, e possíveis pontos de falha.
            """),
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='list_automessages',
            description=textwrap.dedent("""\
                Lista os AutoMessages configurados no banco para uma loja ou empresa.
                Mostra: event_type, message_text, buttons, prioridade, ativo/inativo.
                Use para saber quais templates existem e se estão mapeados para intents.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Slug da loja (ex: ce-saladas)'},
                    'event_type': {'type': 'string', 'description': 'Filtrar por event_type (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='list_agents',
            description=textwrap.dedent("""\
                Lista todos os agentes LLM cadastrados no banco.
                Mostra: provider, model, temperatura, max_tokens, contas associadas,
                se está ativo e qual CompanyProfile usa cada agente.
            """),
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='get_company_profile',
            description=textwrap.dedent("""\
                Retorna a configuração completa de automação de uma loja:
                CompanyProfile (auto_reply, use_ai_agent, default_agent),
                agente LLM associado, AutoMessages ativos, store configurada.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Slug da loja'},
                },
                'required': ['store_slug'],
            },
        ),
        Tool(
            name='get_store_context',
            description=textwrap.dedent("""\
                Resolve o contexto de automação para uma conta WhatsApp ou loja.
                Retorna: store resolvida, CompanyProfile, agente padrão, LLM habilitado.
                Use para debugar "por que o agente não está sendo invocado".
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Slug da loja (opcional)'},
                    'account_id': {'type': 'string', 'description': 'UUID da WhatsAppAccount (opcional)'},
                },
                'required': [],
            },
        ),
        Tool(
            name='debug_message',
            description=textwrap.dedent("""\
                Simula o processamento completo de uma mensagem pelo pipeline:
                  1. Detecção de intent
                  2. Handler escolhido
                  3. Template disponível
                  4. LLM habilitado?
                  5. Resposta gerada (sem enviar ao WhatsApp)
                Retorna cada etapa com resultado e possíveis erros.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'message_text': {'type': 'string', 'description': 'Texto da mensagem do cliente'},
                    'store_slug': {'type': 'string', 'description': 'Slug da loja para contexto'},
                    'phone_number': {'type': 'string', 'description': 'Número do cliente (ex: +5511999999999)'},
                },
                'required': ['message_text', 'store_slug'],
            },
        ),
        Tool(
            name='detect_intent',
            description=textwrap.dedent("""\
                Roda apenas a etapa de detecção de intent em um texto.
                Retorna: intent detectado, confiança, entidades extraídas,
                se foi via regex ou LLM, e qual pattern fez match.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'text': {'type': 'string', 'description': 'Texto para detectar intent'},
                },
                'required': ['text'],
            },
        ),
        Tool(
            name='get_session',
            description=textwrap.dedent("""\
                Retorna a sessão ativa de um número de telefone.
                Mostra: status, carrinho, PIX pendente, histórico de estados.
                Útil para debugar problemas de fluxo de pedido.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'phone_number': {'type': 'string', 'description': 'Ex: +5511999999999'},
                    'store_slug': {'type': 'string', 'description': 'Slug da loja (opcional)'},
                },
                'required': ['phone_number'],
            },
        ),
        Tool(
            name='trace_conversation',
            description=textwrap.dedent("""\
                Retorna as últimas N mensagens de uma conversa (inbound + outbound).
                Mostra: direção, texto, timestamp, status, se foi processada por agente.
                Útil para entender o que o bot respondeu e por quê.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'phone_number': {'type': 'string', 'description': 'Número do cliente'},
                    'limit': {'type': 'integer', 'default': 20, 'description': 'Número de mensagens'},
                },
                'required': ['phone_number'],
            },
        ),
        Tool(
            name='list_active_sessions',
            description=textwrap.dedent("""\
                Lista sessões ativas com carrinho criado ou pagamento pendente.
                Mostra totais por status e as mais recentes.
                Útil para monitorar o volume de clientes em fluxo ativo.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Filtrar por loja (opcional)'},
                    'limit': {'type': 'integer', 'default': 20},
                },
                'required': [],
            },
        ),
        Tool(
            name='list_flows',
            description='Lista os fluxos de bot (AgentFlow) configurados e suas sessões ativas.',
            inputSchema={'type': 'object', 'properties': {}, 'required': []},
        ),
        Tool(
            name='check_store_products',
            description=textwrap.dedent("""\
                Lista produtos ativos de uma loja com nome, preço e categoria.
                Use para verificar se o cardápio está correto e se os produtos
                usados nos handlers/keyword_mappings existem no banco.
            """),
            inputSchema={
                'type': 'object',
                'properties': {
                    'store_slug': {'type': 'string', 'description': 'Slug da loja'},
                    'search': {'type': 'string', 'description': 'Filtrar por nome (opcional)'},
                },
                'required': ['store_slug'],
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  IMPLEMENTAÇÕES
# ══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == 'pipeline_overview':
            return await _pipeline_overview()
        elif name == 'pipeline_health':
            return await _pipeline_health()
        elif name == 'pipeline_stats':
            return await _pipeline_stats(arguments)
        elif name == 'list_intent_patterns':
            return await _list_intent_patterns(arguments)
        elif name == 'list_handlers':
            return await _list_handlers()
        elif name == 'list_automessages':
            return await _list_automessages(arguments)
        elif name == 'list_agents':
            return await _list_agents()
        elif name == 'get_company_profile':
            return await _get_company_profile(arguments)
        elif name == 'get_store_context':
            return await _get_store_context(arguments)
        elif name == 'debug_message':
            return await _debug_message(arguments)
        elif name == 'detect_intent':
            return await _detect_intent(arguments)
        elif name == 'get_session':
            return await _get_session(arguments)
        elif name == 'trace_conversation':
            return await _trace_conversation(arguments)
        elif name == 'list_active_sessions':
            return await _list_active_sessions(arguments)
        elif name == 'list_flows':
            return await _list_flows()
        elif name == 'check_store_products':
            return await _check_store_products(arguments)
        else:
            return _err(f'Ferramenta desconhecida: {name}')
    except Exception as exc:
        import traceback
        return _err(f'{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}')


# ─── pipeline_overview ────────────────────────────────────────────────────────

async def _pipeline_overview() -> list[TextContent]:
    return _ok({
        'pipeline': {
            'nome': 'WhatsApp Bot Pipeline — Pastita',
            'etapas': [
                {
                    'ordem': 1,
                    'nome': 'Webhook Verification',
                    'arquivo': 'apps/whatsapp/services/webhook_service.py',
                    'o_que_faz': 'Verifica assinatura HMAC-SHA256 do Meta, registra WebhookEvent, garante idempotência via event_id',
                    'pode_falhar': ['Assinatura inválida → 403', 'DB unavailable → 500', 'Evento duplicado → ignorado (OK)'],
                },
                {
                    'ordem': 2,
                    'nome': 'Conversation Get/Create',
                    'arquivo': 'apps/conversations/services.py',
                    'o_que_faz': 'Resolve conversa existente ou cria nova para o número de telefone',
                    'pode_falhar': ['Race condition na criação simultânea (mitigado com get_or_create)', 'Número sem formato E.164 → conversa não linkada'],
                },
                {
                    'ordem': 3,
                    'nome': 'Intent Detection',
                    'arquivo': 'apps/whatsapp/intents/detector.py',
                    'o_que_faz': 'Regex-first (80% dos casos, zero custo) → LLM fallback com NVIDIA Llama 3.1 70B (20%)',
                    'intents_nivel_1': 'greeting, price_check, business_hours, delivery_info, menu_request, track_order, payment_status, location, contact, faq',
                    'intents_nivel_2': 'create_order, cancel_order, confirm_payment, request_pix, view_qr_code, copy_pix, add_to_cart, product_mention',
                    'intents_nivel_3_llm': 'product_inquiry, customization, comparison, recommendation, complaint, general_question',
                    'bug_conhecido': 'interactive_reply (cliente clicou em botão de lista) NÃO é processado como intent → cai em UNKNOWN',
                    'pode_falhar': ['NVIDIA API timeout → UNKNOWN intent', 'Regex não cobre variações regionais'],
                },
                {
                    'ordem': 4,
                    'nome': 'Context Resolution',
                    'arquivo': 'apps/automation/services/context_service.py',
                    'o_que_faz': 'Resolve Store → CompanyProfile → WhatsAppAccount → Agent para a mensagem',
                    'pode_falhar': ['CompanyProfile sem store E sem account → bloqueado pelo CheckConstraint (migration 0013)', 'Loja sem CompanyProfile → agente e templates indisponíveis'],
                },
                {
                    'ordem': 5,
                    'nome': 'UnifiedService (Orchestrador)',
                    'arquivo': 'apps/automation/services/unified_service.py',
                    'o_que_faz': 'Handler → Template DB → LLM → Fallback (nessa ordem de prioridade)',
                    'thread_timeout': '10 segundos — se exceder, entra no fallback do agente LLM direto',
                    'metricas': 'unified.source, unified.intent, unified.duration_ms logados como structured log',
                    'pode_falhar': ['Handler com self.store=None → tratado com null check (fixado)', 'Template com placeholder inválido → logado como warning, não crasha', 'LLM error → silencioso, continua pro fallback'],
                },
                {
                    'ordem': 6,
                    'nome': 'Intent Handlers',
                    'arquivo': 'apps/whatsapp/intents/handlers.py',
                    'o_que_faz': 'Respostas determinísticas para cada intent (sem LLM)',
                    'handlers_criticos': {
                        'MenuRequestHandler': 'Busca produtos do DB → lista interativa WhatsApp (máx 10 itens)',
                        'CreateOrderHandler': 'Extrai produtos do texto via regex + keyword_mappings → cria pedido real + PIX',
                        'QuickOrderHandler': 'Mesmo que CreateOrder mas direto da mensagem original',
                        'ProductMentionHandler': 'Cliente digitou nome de produto sem quantidade → mostra tipos disponíveis',
                    },
                    'bug_critico': 'keyword_mappings hardcoded (rondelli, lasanha, nhoque, bolonhesa) — não funciona para outras lojas ou novos produtos',
                    'pode_falhar': ['Produto não encontrado → mensagem de "não existe" (falso negativo frequente)', 'self.store=None → tratado com guard (fixado)'],
                },
                {
                    'ordem': 7,
                    'nome': 'AutoMessage Templates',
                    'arquivo': 'apps/automation/models.py (AutoMessage)',
                    'o_que_faz': 'Templates configurados pelo operador no banco, mapeados por event_type',
                    'mapeamento_intent_event': {
                        'GREETING': 'welcome',
                        'MENU_REQUEST': 'menu',
                        'ADD_TO_CART': 'cart_created',
                        'CREATE_ORDER': 'order_received',
                        'TRACK_ORDER': 'order_confirmed',
                        'PAYMENT_STATUS': 'payment_confirmed',
                    },
                    'pode_falhar': ['Nenhum template cadastrado → vai direto pro LLM ou fallback', 'Template com buttons inválidos → validados e filtrados (fixado)'],
                },
                {
                    'ordem': 8,
                    'nome': 'LangchainService (Agente LLM)',
                    'arquivo': 'apps/agents/services.py',
                    'o_que_faz': 'Chama provider LLM (Kimi/OpenAI/Anthropic/NVIDIA) com contexto da loja e histórico da conversa',
                    'providers': ['kimi', 'openai', 'anthropic', 'ollama', 'nvidia'],
                    'contexto_injetado': 'Cardápio (20 produtos), dados do cliente, carrinho atual, intenção detectada',
                    'pode_falhar': ['API key ausente → BaseAPIException imediata', 'Timeout → None retornado, pipeline continua pro fallback', 'Loja não resolvida → contexto vazio (pastita fallback REMOVIDO)'],
                },
                {
                    'ordem': 9,
                    'nome': 'Response Dispatch',
                    'arquivo': 'apps/whatsapp/services/webhook_service.py (post_process_inbound_message)',
                    'o_que_faz': 'Envia resposta interativa (botões/lista) ou enfileira texto via Celery',
                    'pipeline_dropped_alert': 'Se nenhum path funcionou → log ERROR com pipeline.dropped=True',
                    'pode_falhar': ['WhatsApp API rate limit → falha silenciosa sem retry automático', 'Celery unavailable → mensagem não enviada'],
                },
            ],
            'celery_beat_tasks': {
                'check-abandoned-carts': '5min — notifica carrinhos abandonados',
                'check-pending-pix-payments': '10min — lembra clientes com PIX pendente',
                'process-scheduled-messages': '1min — processa mensagens agendadas',
                'cleanup-intent-logs': 'daily — remove logs > 30 dias',
                'cleanup-expired-sessions': 'daily — expira sessões inativas > 7 dias',
            },
        }
    })


# ─── pipeline_health ──────────────────────────────────────────────────────────

async def _pipeline_health() -> list[TextContent]:
    from apps.automation.services.pipeline_health import health_check
    return _ok(health_check())


# ─── pipeline_stats ───────────────────────────────────────────────────────────

async def _pipeline_stats(args: dict) -> list[TextContent]:
    from apps.automation.services.pipeline_health import get_pipeline_stats
    hours = int(args.get('hours', 24))
    return _ok(get_pipeline_stats(hours=hours))


# ─── list_intent_patterns ────────────────────────────────────────────────────

async def _list_intent_patterns(args: dict) -> list[TextContent]:
    from apps.whatsapp.intents.detector import IntentDetector, IntentType
    from apps.automation.services.unified_service import UnifiedService

    filter_intent = args.get('filter_intent', '').lower()
    detector = IntentDetector(use_llm_fallback=False)

    # Mapeamento intent → event (replicado aqui para referência)
    intent_event_map = {
        'GREETING': 'welcome',
        'MENU_REQUEST': 'menu',
        'PRODUCT_INQUIRY': 'menu',
        'PRODUCT_MENTION': 'menu',
        'ADD_TO_CART': 'cart_created',
        'CREATE_ORDER': 'order_received',
        'TRACK_ORDER': 'order_confirmed',
        'PAYMENT_STATUS': 'payment_confirmed',
        'REQUEST_PIX': 'pix_generated',
        'CONFIRM_PAYMENT': 'payment_confirmed',
        'BUSINESS_HOURS': 'business_hours',
        'LOCATION': 'business_hours',
        'FAQ': 'faq',
        'UNKNOWN': 'welcome',
    }

    result = {}
    for intent_type, patterns in detector.PATTERNS.items():
        name = intent_type.value
        if filter_intent and filter_intent not in name:
            continue
        result[name] = {
            'patterns': patterns,
            'automessage_event': intent_event_map.get(intent_type.name, '—'),
            'nivel': (
                'nivel_1_template' if intent_type.name in {
                    'GREETING', 'PRICE_CHECK', 'BUSINESS_HOURS', 'DELIVERY_INFO',
                    'MENU_REQUEST', 'TRACK_ORDER', 'PAYMENT_STATUS', 'LOCATION', 'CONTACT', 'FAQ'
                } else
                'nivel_2_acao_direta' if intent_type.name in {
                    'CREATE_ORDER', 'CANCEL_ORDER', 'CONFIRM_PAYMENT', 'REQUEST_PIX',
                    'VIEW_QR_CODE', 'COPY_PIX', 'ADD_TO_CART', 'PRODUCT_MENTION', 'HUMAN_HANDOFF'
                } else
                'nivel_3_llm'
            ),
        }
    return _ok({'total_intents': len(result), 'intents': result})


# ─── list_handlers ────────────────────────────────────────────────────────────

async def _list_handlers() -> list[TextContent]:
    from apps.whatsapp.intents.handlers import HANDLER_MAP

    result = {}
    for intent_type, handler_cls in HANDLER_MAP.items():
        uses_store = any(
            'self.store' in (getattr(method, '__code__', None) and method.__code__.co_consts.__str__() or '')
            for method in [getattr(handler_cls, 'handle', None)]
            if callable(method)
        )
        result[intent_type.value] = {
            'handler_class': handler_cls.__name__,
            'docstring': (handler_cls.__doc__ or '').strip(),
        }

    # Status de bugs conhecidos e melhorias implementadas
    result['_status'] = {
        'InteractiveReplyHandler': {
            'status': '✅ IMPLEMENTADO',
            'descricao': 'Handler dedicado para cliques em botões e listas interativas do WhatsApp.',
            'roteia': ['product_<uuid> → pergunta quantidade', 'add_<uuid>_<qty> → cria pedido', 'view_menu → cardápio', 'start_order → pedido', 'track_<id> → rastreamento', 'contact_support → handoff'],
        },
        'CreateOrderHandler._parse_items_from_text': {
            'status': '✅ CORRIGIDO',
            'descricao': 'Busca dinâmica no banco — sem keywords hardcoded. Funciona para qualquer loja e qualquer produto.',
        },
        'UnifiedService.process_message': {
            'status': '✅ ATUALIZADO',
            'descricao': 'Aceita interactive_reply=dict. Se presente, roteia para InteractiveReplyHandler diretamente, sem detecção de intent.',
        },
        'UnknownHandler': {
            'status': '✅ MELHORADO',
            'descricao': 'Se mensagem é só um número (e.g. "2"), verifica pending_product_id na sessão e cria pedido.',
        },
        'webhook_service.post_process_inbound_message': {
            'status': '✅ ATUALIZADO',
            'descricao': 'Extrai list_reply/button_reply de message.content antes do orquestrador e passa como interactive_reply.',
        },
        'ProductMentionHandler': {
            'aviso': 'Remove palavras "de", "com", "e" do search_term — pode quebrar nomes compostos muito curtos',
        },
    }
    return _ok(result)


# ─── list_automessages ────────────────────────────────────────────────────────

async def _list_automessages(args: dict) -> list[TextContent]:
    from apps.automation.models import AutoMessage
    from apps.stores.models import Store

    store_slug = args.get('store_slug')
    event_type = args.get('event_type')

    qs = AutoMessage.objects.select_related('company').all()

    if store_slug:
        try:
            store = Store.objects.get(slug=store_slug)
            qs = qs.filter(company__store=store)
        except Store.DoesNotExist:
            return _err(f'Loja não encontrada: {store_slug}')

    if event_type:
        qs = qs.filter(event_type=event_type)

    items = []
    for msg in qs.order_by('event_type', 'priority')[:100]:
        items.append({
            'id': str(msg.id),
            'event_type': msg.event_type,
            'name': msg.name,
            'is_active': msg.is_active,
            'priority': msg.priority,
            'message_text': msg.message_text[:200] + ('...' if len(msg.message_text) > 200 else ''),
            'has_buttons': bool(msg.buttons),
            'buttons_count': len(msg.buttons) if msg.buttons else 0,
            'company': str(msg.company_id),
            'trigger_delay_seconds': getattr(msg, 'delay_seconds', None),
        })

    event_types_missing = []
    configured_events = {m['event_type'] for m in items}
    expected_events = ['welcome', 'menu', 'cart_created', 'order_received', 'order_confirmed', 'payment_confirmed', 'pix_generated']
    for ev in expected_events:
        if ev not in configured_events:
            event_types_missing.append(ev)

    return _ok({
        'total': len(items),
        'automessages': items,
        'event_types_nao_configurados': event_types_missing,
        'aviso': 'Se event_types_nao_configurados não estiver vazio, o pipeline vai para LLM ou fallback para esses intents' if event_types_missing else None,
    })


# ─── list_agents ──────────────────────────────────────────────────────────────

async def _list_agents() -> list[TextContent]:
    from apps.agents.models import Agent

    agents = []
    for agent in Agent.objects.prefetch_related('accounts').all():
        agents.append({
            'id': str(agent.id),
            'name': agent.name,
            'provider': agent.provider,
            'model_name': agent.model_name,
            'is_active': agent.is_active,
            'temperature': float(agent.temperature),
            'max_tokens': agent.max_tokens,
            'timeout': agent.timeout,
            'has_api_key': bool(agent.api_key),
            'base_url': agent.base_url or '(padrão do provider)',
            'accounts_count': agent.accounts.count(),
            'system_prompt_chars': len(agent.system_prompt or ''),
            'context_prompt_chars': len(getattr(agent, 'context_prompt', '') or ''),
        })

    return _ok({
        'total': len(agents),
        'agents': agents,
        'aviso_sem_agentes': 'Nenhum agente LLM ativo — o pipeline vai ao fallback para todas as mensagens' if not any(a['is_active'] for a in agents) else None,
    })


# ─── get_company_profile ─────────────────────────────────────────────────────

async def _get_company_profile(args: dict) -> list[TextContent]:
    from apps.stores.models import Store
    from apps.automation.models import CompanyProfile, AutoMessage

    store_slug = args['store_slug']
    try:
        store = Store.objects.select_related('automation_profile').get(slug=store_slug)
    except Store.DoesNotExist:
        return _err(f'Loja não encontrada: {store_slug}')

    try:
        profile = store.automation_profile
    except Exception:
        return _ok({
            'store': store_slug,
            'erro': 'Sem CompanyProfile — automação não vai funcionar. Crie um CompanyProfile para esta loja.',
        })

    agent_info = None
    if profile.default_agent:
        a = profile.default_agent
        agent_info = {
            'id': str(a.id),
            'name': a.name,
            'provider': a.provider,
            'model': a.model_name,
            'is_active': a.is_active,
        }

    automessages_count = AutoMessage.objects.filter(company=profile, is_active=True).count()

    return _ok({
        'store': store_slug,
        'company_profile_id': str(profile.id),
        'auto_reply_enabled': profile.auto_reply_enabled,
        'welcome_message_enabled': profile.welcome_message_enabled,
        'use_ai_agent': profile.use_ai_agent,
        'menu_auto_send': profile.menu_auto_send,
        'default_agent': agent_info,
        'automessages_ativos': automessages_count,
        'abandoned_cart_notification': profile.abandoned_cart_notification,
        'abandoned_cart_delay_minutes': profile.abandoned_cart_delay_minutes,
        'pix_notification_enabled': profile.pix_notification_enabled,
        'diagnostico': {
            'llm_vai_funcionar': bool(profile.use_ai_agent and agent_info and agent_info['is_active']),
            'templates_configurados': automessages_count > 0,
            'problema': (
                'use_ai_agent=False — agente LLM desabilitado' if not profile.use_ai_agent else
                'Sem default_agent configurado' if not agent_info else
                'Agente inativo' if not agent_info['is_active'] else
                'OK'
            ),
        },
    })


# ─── get_store_context ────────────────────────────────────────────────────────

async def _get_store_context(args: dict) -> list[TextContent]:
    from apps.automation.services.context_service import AutomationContextService
    from apps.stores.models import Store
    from apps.whatsapp.models import WhatsAppAccount

    store = None
    account = None

    if args.get('store_slug'):
        try:
            store = Store.objects.get(slug=args['store_slug'])
        except Store.DoesNotExist:
            return _err(f"Loja não encontrada: {args['store_slug']}")

    if args.get('account_id'):
        try:
            account = WhatsAppAccount.objects.get(id=args['account_id'])
        except WhatsAppAccount.DoesNotExist:
            return _err(f"WhatsAppAccount não encontrada: {args['account_id']}")

    if not store and not account:
        return _err('Forneça store_slug ou account_id')

    kwargs = {}
    if account:
        kwargs['account'] = account
    if store:
        kwargs['store'] = store

    ctx = AutomationContextService.resolve(create_profile=False, **kwargs)
    agent = AutomationContextService.get_default_agent(context=ctx)
    llm_enabled = AutomationContextService.is_ai_enabled(context=ctx)

    return _ok({
        'store': str(ctx.store) if ctx.store else None,
        'store_id': str(ctx.store.id) if ctx.store else None,
        'profile_id': str(ctx.profile.id) if ctx.profile else None,
        'account_id': str(ctx.account.id) if ctx.account else None,
        'agent': {'id': str(agent.id), 'name': agent.name, 'provider': agent.provider} if agent else None,
        'llm_enabled': llm_enabled,
        'diagnostico': {
            'tem_store': ctx.store is not None,
            'tem_profile': ctx.profile is not None,
            'tem_agent': agent is not None,
            'llm_ativo': llm_enabled,
            'problema': (
                'Sem store — handlers e cardápio não vão funcionar' if not ctx.store else
                'Sem CompanyProfile — templates e configuração ausentes' if not ctx.profile else
                'Sem agente — LLM desabilitado' if not agent else
                'LLM desabilitado na conta/perfil' if not llm_enabled else
                'Contexto OK'
            ),
        },
    })


# ─── debug_message ────────────────────────────────────────────────────────────

async def _debug_message(args: dict) -> list[TextContent]:
    from apps.whatsapp.intents.detector import IntentDetector
    from apps.whatsapp.intents.handlers import HANDLER_MAP, get_handler
    from apps.automation.models import AutoMessage
    from apps.stores.models import Store

    message_text = args['message_text']
    store_slug = args['store_slug']
    phone_number = args.get('phone_number', '+5511000000000')

    trace = {'message': message_text, 'store': store_slug, 'etapas': []}

    # Etapa 1: Intent Detection
    detector = IntentDetector(use_llm_fallback=False)
    intent_data = detector.detect(message_text.lower())
    intent = intent_data.get('intent')
    trace['etapas'].append({
        'etapa': '1_intent_detection',
        'resultado': intent.value if intent else 'none',
        'dados': {k: str(v) for k, v in intent_data.items()},
        'via': 'regex (LLM desabilitado no debug)',
    })

    # Etapa 2: Handler
    handler_cls = HANDLER_MAP.get(intent) if intent else None
    if handler_cls:
        trace['etapas'].append({
            'etapa': '2_handler',
            'resultado': handler_cls.__name__,
            'nota': 'Handler encontrado — resposta determinística disponível',
        })
    else:
        trace['etapas'].append({
            'etapa': '2_handler',
            'resultado': 'nenhum',
            'nota': 'Nenhum handler para este intent',
        })

    # Etapa 3: AutoMessage Template
    try:
        store = Store.objects.get(slug=store_slug)
        profile = store.automation_profile

        event_map = {
            'greeting': 'welcome', 'menu_request': 'menu', 'product_mention': 'menu',
            'add_to_cart': 'cart_created', 'create_order': 'order_received',
            'track_order': 'order_confirmed', 'payment_status': 'payment_confirmed',
        }
        event_type = event_map.get(intent.value if intent else '', '')
        template = None
        if event_type:
            template = AutoMessage.objects.filter(
                company=profile, event_type=event_type, is_active=True
            ).order_by('priority').first()

        trace['etapas'].append({
            'etapa': '3_automessage_template',
            'event_type_buscado': event_type or '(não mapeado)',
            'resultado': f'template encontrado: {template.name}' if template else 'nenhum template',
            'template_id': str(template.id) if template else None,
        })
    except Exception as exc:
        trace['etapas'].append({
            'etapa': '3_automessage_template',
            'resultado': 'erro',
            'erro': str(exc),
        })

    # Etapa 4: LLM disponível?
    try:
        store = Store.objects.get(slug=store_slug)
        profile = store.automation_profile
        agent = profile.default_agent
        trace['etapas'].append({
            'etapa': '4_llm_disponivel',
            'use_ai_agent': profile.use_ai_agent,
            'agente': agent.name if agent else None,
            'agente_ativo': agent.is_active if agent else False,
            'llm_vai_ser_chamado': bool(profile.use_ai_agent and agent and agent.is_active),
        })
    except Exception as exc:
        trace['etapas'].append({'etapa': '4_llm_disponivel', 'erro': str(exc)})

    # Diagnóstico final
    trace['diagnostico'] = {
        'intent_detectado': intent.value if intent else 'none',
        'handler_disponivel': handler_cls is not None,
        'resposta_esperada': (
            f'Handler: {handler_cls.__name__}' if handler_cls else
            'Template DB' if trace['etapas'][2].get('template_id') else
            'Agente LLM' if trace['etapas'][3].get('llm_vai_ser_chamado') else
            'FALLBACK GENÉRICO — nenhum provider vai responder adequadamente'
        ),
        'alerta': (
            'PROBLEMA: intent=UNKNOWN — mensagem não reconhecida pelo detector. Verifique os regex patterns.'
            if intent and intent.value == 'unknown' else
            'PROBLEMA: interactive_reply não processado — se esta mensagem veio de clique em botão/lista, adicione handler de interactive_reply.'
            if message_text.startswith('product_') else
            None
        ),
    }

    return _ok(trace)


# ─── detect_intent ────────────────────────────────────────────────────────────

async def _detect_intent(args: dict) -> list[TextContent]:
    import re
    from apps.whatsapp.intents.detector import IntentDetector

    text = args['text']
    detector = IntentDetector(use_llm_fallback=False)

    # Roda detecção
    intent_data = detector.detect(text.lower())

    # Descobre qual pattern fez match
    matched_pattern = None
    matched_intent = None
    for intent_type, patterns in detector.PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text.lower()):
                matched_pattern = pattern
                matched_intent = intent_type.value
                break
        if matched_pattern:
            break

    return _ok({
        'texto_original': text,
        'texto_normalizado': text.lower(),
        'intent_detectado': intent_data.get('intent').value if intent_data.get('intent') else 'none',
        'confianca': intent_data.get('confidence', 0),
        'entidades': intent_data.get('entities', {}),
        'pattern_que_fez_match': matched_pattern,
        'intent_do_match': matched_intent,
        'via_llm': intent_data.get('via_llm', False),
        'mensagem_original': intent_data.get('original_message', text),
    })


# ─── get_session ──────────────────────────────────────────────────────────────

async def _get_session(args: dict) -> list[TextContent]:
    from apps.automation.models import CustomerSession
    from apps.stores.models import Store

    phone = args['phone_number']
    store_slug = args.get('store_slug')

    qs = CustomerSession.objects.filter(phone_number=phone).order_by('-updated_at')

    if store_slug:
        try:
            store = Store.objects.get(slug=store_slug)
            qs = qs.filter(company__store=store)
        except Store.DoesNotExist:
            return _err(f'Loja não encontrada: {store_slug}')

    sessions = []
    for s in qs[:5]:
        sessions.append({
            'id': str(s.id),
            'status': s.status,
            'cart_items_count': s.cart_items_count,
            'cart_total': float(s.cart_total or 0),
            'has_cart': bool(s.cart_data),
            'has_pix': bool(getattr(s, 'pix_code', '')),
            'pix_expiry': getattr(s, 'pix_expires_at', None),
            'order_id': getattr(s, 'external_order_id', None),
            'created_at': s.created_at,
            'updated_at': s.updated_at,
            'last_activity_at': getattr(s, 'last_activity_at', None),
        })

    return _ok({
        'phone_number': phone,
        'sessions_encontradas': len(sessions),
        'sessions': sessions,
        'aviso': 'Sem sessão ativa — próxima mensagem inicia uma nova' if not sessions else None,
    })


# ─── trace_conversation ───────────────────────────────────────────────────────

async def _trace_conversation(args: dict) -> list[TextContent]:
    from apps.whatsapp.models import Message

    phone = args['phone_number']
    limit = int(args.get('limit', 20))

    messages = (
        Message.objects
        .filter(conversation__phone_number=phone)
        .select_related('conversation')
        .order_by('-created_at')[:limit]
    )

    result = []
    for msg in messages:
        result.append({
            'id': str(msg.id),
            'direction': msg.direction,
            'body': (msg.body or '')[:300],
            'message_type': msg.message_type,
            'status': msg.status,
            'processed_by_agent': getattr(msg, 'processed_by_agent', None),
            'created_at': msg.created_at,
            'whatsapp_message_id': getattr(msg, 'whatsapp_message_id', None),
        })

    return _ok({
        'phone_number': phone,
        'mensagens': result[::-1],  # cronológico
        'total_retornado': len(result),
        'dica': 'Use processed_by_agent=True para ver quais mensagens foram respondidas pelo agente LLM',
    })


# ─── list_active_sessions ────────────────────────────────────────────────────

async def _list_active_sessions(args: dict) -> list[TextContent]:
    from apps.automation.models import CustomerSession
    from apps.stores.models import Store

    store_slug = args.get('store_slug')
    limit = int(args.get('limit', 20))

    active_statuses = [
        CustomerSession.SessionStatus.CART_CREATED,
        CustomerSession.SessionStatus.CHECKOUT,
        CustomerSession.SessionStatus.PAYMENT_PENDING,
    ]

    qs = CustomerSession.objects.filter(status__in=active_statuses)

    if store_slug:
        try:
            store = Store.objects.get(slug=store_slug)
            qs = qs.filter(company__store=store)
        except Store.DoesNotExist:
            return _err(f'Loja não encontrada: {store_slug}')

    from django.db.models import Count
    totals = {
        s: qs.filter(status=s).count()
        for s in [
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CHECKOUT,
            CustomerSession.SessionStatus.PAYMENT_PENDING,
        ]
    }

    sessions = []
    for s in qs.order_by('-updated_at')[:limit]:
        sessions.append({
            'id': str(s.id),
            'phone_number': s.phone_number,
            'status': s.status,
            'cart_total': float(s.cart_total or 0),
            'cart_items_count': s.cart_items_count,
            'updated_at': s.updated_at,
        })

    return _ok({
        'totais_por_status': totals,
        'total_ativo': sum(totals.values()),
        'sessions': sessions,
    })


# ─── list_flows ───────────────────────────────────────────────────────────────

async def _list_flows() -> list[TextContent]:
    try:
        from apps.automation.models import AgentFlow, FlowSession

        flows = []
        for flow in AgentFlow.objects.all():
            active_sessions = FlowSession.objects.filter(flow=flow, is_expired=False).count()
            flows.append({
                'id': str(flow.id),
                'name': flow.name,
                'is_active': getattr(flow, 'is_active', True),
                'active_sessions': active_sessions,
                'nodes_count': len(flow.nodes) if isinstance(getattr(flow, 'nodes', None), (list, dict)) else '?',
            })
        return _ok({'total': len(flows), 'flows': flows})
    except Exception as exc:
        return _ok({'aviso': f'AgentFlow não disponível: {exc}', 'flows': []})


# ─── check_store_products ────────────────────────────────────────────────────

async def _check_store_products(args: dict) -> list[TextContent]:
    from apps.stores.models import Store, StoreProduct

    store_slug = args['store_slug']
    search = args.get('search', '')

    try:
        store = Store.objects.get(slug=store_slug)
    except Store.DoesNotExist:
        return _err(f'Loja não encontrada: {store_slug}')

    qs = StoreProduct.objects.filter(store=store, is_active=True).select_related('category')
    if search:
        qs = qs.filter(name__icontains=search)

    products = []
    for p in qs.order_by('category__name', 'name')[:100]:
        products.append({
            'id': str(p.id),
            'name': p.name,
            'price': float(p.price),
            'category': p.category.name if p.category else None,
            'slug': getattr(p, 'slug', None),
            'is_active': p.is_active,
        })

    return _ok({
        'store': store_slug,
        'total_produtos_ativos': len(products),
        'produtos': products,
        'match_strategy': (
            'Busca dinâmica por nome no banco (accent-insensitive substring + first-word + any-word). '
            'Todos os produtos listados acima são reconhecíveis pelo handler.'
        ),
    })


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
