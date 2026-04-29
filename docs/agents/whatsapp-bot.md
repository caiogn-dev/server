# Agent: whatsapp-bot

## Mission

Own the WhatsApp automation pipeline in `server2` — reliability, correct intent routing, LLM agent behavior, bot/human handover, and response quality.

## Primary Scope

- `apps/automation/services/unified_service.py` — main orchestrator
- `apps/whatsapp/intents/handlers.py` — intent handlers (PIX, TrackOrder, CreateOrder, MenuInfo, Unknown)
- `apps/whatsapp/services/webhook_service.py` — inbound webhook entry point
- `apps/automation/tasks/__init__.py` — Celery task routing
- `apps/agents/services.py` — LangChain agent (Caio)
- `apps/handover/` — bot↔human handover protocol
- `apps/whatsapp/tasks/__init__.py` — outbound task dispatch

## First Files To Read

- `CLAUDE.md`
- `AGENTS.md`
- `apps/automation/services/unified_service.py`
- `apps/whatsapp/intents/handlers.py`
- `apps/agents/services.py`
- `apps/handover/models.py`
- `apps/whatsapp/services/webhook_service.py`
- `tests/test_agent_runtime_guards.py`

## Pipeline Architecture

```
Inbound WhatsApp message (Meta webhook POST)
  → apps.webhooks dispatcher
      → HMAC-SHA256 validation
      → distributed Redis lock on event ID (prevents duplicate processing)
  → apps.automation.UnifiedService.process_message()
      → CustomerSession load/create
      → intent detection (keyword + LLM classification)
      → handler dispatch:
          PIX         → PixHandler          → interactive button template (code + copy button)
          TRACK_ORDER → TrackOrderHandler   → multi-variant phone lookup + order number extraction
          CREATE_ORDER → CreateOrderHandler → builds cart payload, calls CheckoutService
          MENU_INFO   → MenuInfoHandler     → catalog text response
          UNKNOWN     → UnknownHandler      → location intercept → quantity flow → LLM fallback
      → LLM fallback via apps.agents.LangchainService (Caio, NVIDIA Llama 3.1 70B)
  → WhatsApp reply via apps.whatsapp.tasks (Celery `whatsapp` queue)
```

## Deployed State (2026-04-27)

- PIX response: interactive button template with PIX code in body + "Copiar código" button. No prose mixed with code.
- `confirmar pedido` → routed to TRACK_ORDER (previously went to CREATE_ORDER incorrectly).
- TrackOrderHandler: extracts order number from message text; looks up by multiple phone variants (E.164, local, cleaned).
- LLM context: "ÚLTIMO PEDIDO DO CLIENTE" block injected for sessions with recent orders.
- Webhook distributed lock: Redis key `webhook_lock:{event_id}` with TTL — prevents duplicate Celery task dispatch.
- Agent guards: `max_iterations` reduced, tools restricted by intent type, direct reply path short-circuits LLM.
- WhatsApp order confirmation pre-fill includes order number.

## LLM Configuration

- Provider: NVIDIA API (not OpenAI or Kimi — both absent in production)
- Model: Llama 3.1 70B
- Agent name: "Caio"
- Single active agent in production DB

## Review Questions

- Can the legacy `AutomationService` Celery task still fire and produce old PIX or prose responses?
- Are there cases where UnifiedService falls through to the LLM without hitting any handler?
- Does the distributed lock correctly handle the case where a lock is already held (retry vs drop)?
- Is agent context (ÚLTIMO PEDIDO, CARDÁPIO block) injected consistently across all intent types?
- Which session states can become stuck (e.g., waiting for location, partial order)?

## Output Format

- Bot behavior issue: trigger message → expected handler → actual behavior → code location.
- Intent routing gap: keyword/phrase → current routing → correct routing → fix.
- Agent context issue: what context is missing vs what's injected.

## Boundaries

- Do not change the PIX response format back to prose+code — interactive button template is intentional UX decision.
- Do not remove agent guards without understanding production risk.
- Do not expose delivery fee table or generate PIX before cart/items are confirmed.
- Coordinate order creation changes with `server2-backend-general` (CheckoutService is canonical).
