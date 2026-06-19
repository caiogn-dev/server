# Messaging & Bot Architecture — server2

> Status: descriptive map of the codebase as it exists on `main` (2026-06-17).
> Purpose: surface every send/receive/dispatch path and the LLM/bot layer before the
> Langchain → LangGraph migration is finished. This document deliberately calls out
> duplication, dead code and the half-migrated state ("a bagunça").
>
> All citations are `path:line` against the real code. Where a line is approximate it
> is marked with `~`.

---

## 0. TL;DR pipeline (happy path)

```
Inbound WhatsApp message (Meta)
        │  POST /webhooks/v1/whatsapp/
        ▼
apps/webhooks/dispatcher.py:54  WebhookDispatcherView
        │  - rate limit (60/min/IP)            dispatcher.py:79
        │  - HMAC X-Hub-Signature-256 verify   dispatcher.py:115 / 314
        │  - dedupe by event_id                dispatcher.py:135
        │  - create WebhookEvent               dispatcher.py:148
        ▼  route by provider
apps/webhooks/handlers/whatsapp_handler.py:20  WhatsAppHandler.handle()
        │  WebhookService.process_webhook()  → creates whatsapp WebhookEvent rows
        ▼  for each event: enqueue Celery
apps/whatsapp/tasks/__init__.py:39  process_webhook_event(event_id)   [queue: whatsapp]
        │  WebhookService.process_event(post_process_inbound=True)
        ▼
apps/whatsapp/services/webhook_service.py:372  post_process_inbound_message()
        │  - get_or_create Conversation
        │  - extract interactive reply / location / payment-proof
        │  - resolve account → store → CompanyProfile
        ▼  run orchestrator IN A THREAD with timeout   webhook_service.py:589-619
apps/automation/services/unified_service.py:655  UnifiedService.process_message()
        │  IntentDetector → IntentHandler → AutoMessage template → LLM → fallback
        ▼  (only when intent is consultative / LLM enabled)   unified_service.py:932
apps/automation/services/unified_service.py:542  _call_llm()
        ▼
apps/agents/services/langgraph_service.py:42  LangGraphService.process_message()
        │  load Redis history → invoke StateGraph → save Redis history
        ▼
apps/agents/graph/graph.py:31  build_agent_graph()
        load_context → sondagem → agent ⇄ execute_tools → extract_response → END
        │  (reuses LangchainService._build_tools / _build_customer_context)
        ▼  response text returned up the stack
webhook_service.py:635  send response:
        │  interactive → _send_unified_interactive() (immediate)
        │  text        → send_agent_response.delay() [Celery queue: default]
        ▼
apps/whatsapp/services/whatsapp_api_service.py:46  requests.request(POST graph.facebook.com)
        → outbound WhatsApp message
```

If the orchestrator times out / errors / produces nothing, there is a **second, legacy
LLM path** (see §3.6):
`webhook_service.py:690 → process_message_with_agent → AgentService.get_agent_response →
LangchainService.process_message` (the old manual agentic while-loop).

---

## 1. Outbound message sending

Every code path that actually puts bytes on a wire.

| Channel | Transport | Function that sends | File:line | Triggered by |
|---|---|---|---|---|
| WhatsApp | Meta Graph API (`requests.request` POST) | `WhatsAppAPIService._make_request` | `apps/whatsapp/services/whatsapp_api_service.py:46` | MessageService, campaigns, automation tasks, send_agent_response |
| Instagram | Meta Graph API (`session.request` POST) | `InstagramAPI._make_request` | `apps/instagram/services/instagram_api.py:54` (via `InstagramDirectService.send_message` `instagram_direct_service.py:155/202`) | dashboard API, `process_instagram_dm` |
| Messenger | Meta Graph API | `MessengerService.send_message` (apps/messaging) | `apps/messaging/...` (live, see §5) | `process_messenger_dm`, broadcasts |
| Email | Resend SDK (`resend.Emails.send`) | `EmailMarketingService.send_campaign` / `send_single_email` | `apps/marketing/services/email_marketing_service.py:297` / `:379` | marketing campaigns, `send_campaign` task |
| Web Push | `pywebpush` (HTTP to subscription endpoint) | `NotificationService._send_web_push` | `apps/notifications/services/notification_service.py:274` | `NotificationService.send_to_users` / notification rules |
| SSE (orders) | `StreamingHttpResponse` `text/event-stream` | `OrderSSEView.get_event_stream` | `apps/core/sse_views.py:225` (yield at `:136`) | client GET `/api/sse/orders/` (poll 3s) |
| SSE (whatsapp) | `StreamingHttpResponse` | `WhatsAppSSEView.get_event_stream` | `apps/core/sse_views.py:374` | client GET `/api/sse/whatsapp/` (poll 2s) |
| WebSocket | Django Channels `group_send` (Redis layer) | `WhatsAppBroadcastService._send_to_group` | `apps/whatsapp/services/broadcast_service.py:42` | `MessageService._update_message_sent` `message_service.py:~802`, payment webhooks, handover |
| Campaign broadcast | loops over recipients → WhatsApp API | `CampaignService.process_campaign_batch` | `apps/campaigns/services/campaign_service.py:285` (sends at `:325/:347/:355/:364`) | `process_campaign` Celery task |

### 1.1 WhatsApp send detail

- Low-level HTTP: `WhatsAppAPIService._make_request` — `whatsapp_api_service.py:31`, actual call `:46`.
  Base URL `https://graph.facebook.com/{WHATSAPP_API_VERSION}` (`config/settings/base.py:335`),
  endpoint `POST /{phone_number_id}/messages`, Bearer auth.
- Typed senders on the same class: `send_text_message` `:118`, `send_template_message` `:169`,
  `send_interactive_buttons` `:199`, `send_interactive_list` `:244`, `send_product_list` `:303`,
  `send_image` `:345`, `send_document` `:347`, `send_audio` `:398`, `send_video` `:433`.
- `MessageService` (`apps/whatsapp/services/message_service.py`) wraps these, persists a `Message`
  row first, then broadcasts the sent status over WebSocket (`_update_message_sent` `~:802`).

### 1.2 SSE vs WebSocket

Two real-time delivery mechanisms coexist by design (WebSocket primary, SSE fallback — per
`CLAUDE.md`):
- WebSocket consumers in `apps/core/consumers.py`: `NotificationConsumer:18`, `ChatConsumer:75`,
  `DashboardConsumer:147`; routing in `apps/core/routing.py`.
- SSE views in `apps/core/sse_views.py` are **polling** generators (DB poll every 2-3s), not
  push — they re-query and yield. This is duplicate machinery vs the Channels layer but is an
  intentional fallback, not dead code.

---

## 2. Inbound + dispatch / triggers

### 2.1 Central webhook dispatcher

`apps/webhooks/dispatcher.py` — `WebhookDispatcherView` (`:54`), endpoint `/webhooks/v1/{provider}/`.

| Step | Where | Notes |
|---|---|---|
| Rate limit 60/min/IP | `:79` | per-IP |
| Parse payload | `:96` | JSON or form |
| HMAC verify **before** DB write | `:115`, `_verify_signature` `:322`, Meta `_verify_meta_signature` `:314` | fail-closed for whatsapp/instagram/messenger/mercadopago (`:116`) |
| Extract event_type | `_extract_event_type` `:196` | |
| Extract event_id | `_extract_event_id` `:253` | |
| Dedupe | `:135` | skips non-FAILED duplicates |
| Persist `WebhookEvent` | `:148` | only after HMAC passes |
| Route to handler | `:160` | |

Signature schemes: Meta uses `X-Hub-Signature-256` (SHA256 HMAC of body); MercadoPago uses
`x-signature` `ts=..,v1=..` with a 300s tolerance (`:51`, verify `:346`). Fallback Meta secrets
`WHATSAPP_APP_SECRET` / `INSTAGRAM_APP_SECRET` / `META_WEBHOOK_APP_SECRET` (`_meta_fallback_secret` `:302`).

Handler registry (`register_default_handlers` `:395`):

| provider | handler | downstream |
|---|---|---|
| whatsapp | `WhatsAppHandler` (`handlers/whatsapp_handler.py:20`) | `WebhookService.process_webhook` → `process_webhook_event.delay` |
| instagram | `InstagramHandler` (`handlers/instagram_handler.py:22`) | `InstagramWebhookService.process_webhook` → `process_instagram_dm.delay` |
| messenger | `MessengerHandler` (`handlers/messenger_handler.py:22`) | `MessengerWebhookService.process_webhook` → `process_messenger_dm.delay` |
| mercadopago | `MercadoPagoHandler` (`handlers/mercadopago_handler.py:81`) | `CheckoutService.process_payment_webhook` |
| toca-delivery | `TocaDeliveryHandler` | updates `StoreOrder.external_delivery_status` |

GET verification (`hub.challenge`) is handled per-handler `handle_verification` with each
provider's `*_WEBHOOK_VERIFY_TOKEN`.

### 2.2 Celery configuration

`config/celery.py`. Queues: `whatsapp`, `agents`, `automation`, `campaigns`, plus `default`.

**Beat schedule (24 entries, `config/celery.py:24-148`):**

| Task | Schedule | Queue |
|---|---|---|
| `apps.whatsapp.tasks.cleanup_old_webhook_events` | 1h | whatsapp |
| `apps.whatsapp.tasks.sync_message_statuses` | 5m | whatsapp |
| `apps.whatsapp.tasks.process_pending_webhook_events` | 30s | whatsapp |
| `apps.whatsapp.tasks.retry_failed_webhook_events` | 5m | whatsapp |
| `apps.automation.tasks.check_abandoned_carts` | 5m | automation |
| `apps.automation.tasks.check_pending_pix_payments` | 10m | automation |
| `apps.automation.tasks.cleanup_expired_sessions` | daily | automation |
| `apps.automation.tasks.scheduled.process_scheduled_messages` | 1m | automation |
| `apps.automation.tasks.scheduled.process_scheduled_reports` | 1h | automation |
| `apps.automation.tasks.scheduled.cleanup_old_reports` | daily | automation |
| `apps.marketing.tasks.process_scheduled_automations` | 1m | default |
| `apps.campaigns.tasks.check_scheduled_campaigns` | 1m | campaigns |
| `apps.instagram.tasks.refresh_instagram_tokens` | daily | default |
| `apps.automation.tasks.scheduled.cleanup_intent_logs` | daily (days_to_keep=30) | automation |
| `apps.whatsapp.tasks.check_abandoned_store_carts` | 15m | whatsapp |
| `apps.whatsapp.tasks.check_abandoned_whatsapp_sessions` | 5m | whatsapp |
| `apps.whatsapp.tasks.check_inactive_customers` | crontab 11:00 | whatsapp |
| `apps.whatsapp.tasks.check_pending_payments` | 10m | whatsapp |
| `apps.stores.tasks.sync_toca_delivery_statuses` | 1m | default |
| `apps.agents.tasks.learn_all_active_agents` | 6h | agents |
| `apps.agents.tasks.decay_stale_knowledge` | daily | agents |
| `apps.stores.tasks.cleanup_abandoned_carts` | daily | default |
| `apps.stores.tasks.daily_database_backup` | crontab 02:00 | default |
| `apps.stores.tasks.database_integrity_check` | 6h | default |

**Tasks that actually SEND messages** (selected — full list of every task is in §6 of the
agent findings; the message-sending ones are):

| Task | File:line | Sends |
|---|---|---|
| `process_message_with_agent` | `whatsapp/tasks/__init__.py:89` | LLM reply (legacy path, see §3.6) |
| `send_agent_response` | `whatsapp/tasks/__init__.py:213` | WhatsApp text/template/buttons |
| `send_payment_reminder` | `whatsapp/tasks/automation_tasks.py:36` | WhatsApp PIX reminder (30m/2h/24h) |
| `send_cart_reminder` | `whatsapp/tasks/automation_tasks.py:181` | WhatsApp cart reminder |
| `send_session_cart_reminder` | `whatsapp/tasks/automation_tasks.py:524` | WhatsApp session reminder |
| `notify_order_status_change` | `whatsapp/tasks/automation_tasks.py:352` | WhatsApp status update |
| `request_feedback` | `whatsapp/tasks/automation_tasks.py:453` | WhatsApp feedback request |
| `send_reengagement_message` | `whatsapp/tasks/automation_tasks.py:661` | WhatsApp "we miss you" |
| `send_scheduled_message` | `automation/tasks/scheduled.py:19` | WhatsApp (any type) on schedule |
| `process_instagram_dm` | `instagram/tasks.py:12` | Instagram reply (LLM) |
| `process_messenger_dm` | `messaging/tasks.py:12` | Messenger reply (LLM) |
| `send_campaign` / `process_scheduled_automations` | `marketing/tasks.py:27/10` | Email via Resend |
| `process_campaign` | `campaigns/tasks/__init__.py:15` | WhatsApp broadcast batch |
| `notify_new_order_push` | `stores/tasks.py:10` | Web push to store staff |

> Note: `apps/automation/tasks/__init__.py:46/97` (`send_abandoned_cart_notification`,
> `send_pix_reminder`) are explicitly **DEPRECATED** delegators to `AutomationService._send_notification`.

### 2.3 Automation models & rule dispatch

- Models: `AutoMessage` (`automation/models/messaging.py:121`, `render_message` for `{var}` substitution),
  `ScheduledMessage` (`messaging.py:8`, PENDING→PROCESSING→SENT/FAILED state machine),
  `CustomerSession` (`automation/models/session.py:5`, per-phone cart/payment state machine).
- `AutomationService._send_notification` (`automation/services/automation_service.py:631`) +
  `_send_auto_message` (`:650`): idempotent template lookup → render → resolve WhatsApp account →
  send via `WhatsAppService` (buttons or text) → log `AutomationLog`.
- The runtime decision of *canned message vs LLM* is made inside the **UnifiedService** pipeline
  (§3.3), not in `AutomationService`.

---

## 3. LLM / bot agent layer (the core mess)

### 3.1 Two services, one brain

```
                    ┌──────────────────────────────────────────┐
   LIVE inbound ───▶│ UnifiedService (apps/automation)          │
                    │   _call_llm()  unified_service.py:542     │
                    └───────────────┬──────────────────────────┘
                                    │ instantiates
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │ LangGraphService (apps/agents)            │  ← LIVE LLM path
                    │   process_message() langgraph_service.py:42│
                    │   self._lc = LangchainService(agent)  :30 │
                    └───────────────┬──────────────────────────┘
              builds graph (graph.py:31) │ but reuses LangchainService helpers:
              _build_tools / _build_customer_context / _get_store_for_context / _get_memory
                                    ▼
                    ┌──────────────────────────────────────────┐
   LEGACY inbound ─▶│ LangchainService.process_message()        │  ← LEGACY LLM path
   & /api/agents/   │   langchain_service.py:1451               │     (manual while-loop :1607)
   {id}/process/    │   _build_dynamic_context() :666           │
                    └──────────────────────────────────────────┘
```

`LangchainService` is **not** dead — LangGraphService delegates the heavy lifting (LLM creation,
tools, customer context, Redis memory) to it. What is effectively dead in production is
`LangchainService`'s own **agentic loop** and `_build_dynamic_context`, which only run when the
legacy entry points are used.

### 3.2 LangchainService — `apps/agents/services/langchain_service.py`

| Method | Line | Role | Used by |
|---|---|---|---|
| `_create_llm` | 48 | builds Kimi/OpenAI/Anthropic/Nvidia/Ollama LLM | both paths |
| `_get_memory` | 165 | `RedisChatMessageHistory` key `agent_{id}_{session}` | both paths |
| `_build_customer_context` | 339 | CRM/order context (StoreCustomer, StoreOrder, UnifiedUser) | **SHARED** (LangGraph node + legacy) |
| `_build_dynamic_context` | 666 | monolithic full-context builder + Kimi accent strip | **LEGACY ONLY** (`process_message`, `process_message_stream`) |
| `_build_tools` | 997 | 11 LangChain tools (menu/cart/order/payment), Redis-backed cart | **SHARED** |
| `_get_store_for_context` | 1429 | resolves store from conversation/agent | **SHARED** |
| `process_message` | 1451 | legacy entry; manual agentic while-loop at 1607-1660 (max 5 iters) | legacy only |
| `process_message_stream` | 1746 | streaming variant | **NO live caller found (dead)** |

Tool-call gating is provider-dependent (OpenAI/Anthropic/Nvidia only, `:1585`).
`_resolve_allowed_tools` (`~:593`) narrows tools by intent — **only in the legacy path; the
LangGraph path does NOT apply it** (a guardrail gap).

### 3.3 UnifiedService — `apps/automation/services/unified_service.py`

- Entry `process_message` (`:655`). Priority pipeline:
  1. interactive-reply handler (`:693`)
  2. location handler (`:743`)
  3. checkout-state handler (`:791`)
  4. `IntentDetector.detect()` (`:842`)
  5. out-of-hours template (`:863`)
  6. intent handler (`:880`)
  7. `AutoMessage` template by intent (`:892`)
  8. **LLM** `_call_llm()` (`:932`, defined `:542`) — only for consultative intents
  9. fallback / dead-end handoff (`:956`)
- `_call_llm` instantiates `LangGraphService(self.agent)` at **`:561`**, computes a stable
  `session_id` from `AgentConversation` (`:564`), invokes it (`:580`), then persists/updates
  `AgentConversation` so Redis memory survives across turns (`:598-632`).
- `LLMOrchestratorService = UnifiedService` (alias, `:990`). `UnifiedResponse` dataclass `:72`,
  `ResponseSource` enum (TEMPLATE/LLM/HANDLER/FALLBACK) `:65`.

### 3.4 LangGraphService — `apps/agents/services/langgraph_service.py`

Thin wrapper (`:18`). Ctor builds `LangchainService` (`:30`). `process_message` (`:42`): loads
Redis history (`:61`), builds initial `AgentState` (`:69`), invokes compiled graph (`:83`),
saves history (`:98`), returns the same dict shape as LangchainService. Graph cached via
`_get_graph` → `build_agent_graph` (`:35`).

### 3.5 The graph — `apps/agents/graph/`

`graph.py:31 build_agent_graph` wires 5 nodes (`nodes.py`):

| Node | nodes.py | Behavior |
|---|---|---|
| `load_context` | 196 | resolve store, `_build_customer_context`, `_catalog_summary` (238), `_delivery_summary`, `_load_knowledge_context`, `_build_tools` |
| `sondagem` | 49 | first-turn vague-greeting shortcut, scripted reply, **skips LLM** |
| `agent` | 309 | bind tools, build system prompt (`_SYSTEM_TEMPLATE` :88), invoke LLM |
| `execute_tools` | 360 | run tool_calls, block `buscar_produto` on confirmation words (:374), max 6 iters (`_MAX_TOOL_ITERATIONS`) |
| `extract_response` | 413 | pull final text (handles Anthropic list content) |

Edges (`graph.py:59`): `load_context→sondagem`; `sondagem→{extract_response | agent}`
(`should_skip_llm` :76); `agent→{execute_tools | extract_response}` (`should_use_tools` :398);
`execute_tools→agent`; `extract_response→END`. `AgentState` TypedDict in `graph/state.py:13`
(messages use `add_messages` reducer).

### 3.6 The legacy LLM fallback is still wired into live inbound

This is the most important "mess" finding. Inside the live WhatsApp pipeline,
`webhook_service.py`:

- Runs UnifiedService in a **daemon thread with a timeout** (`:589-619`,
  `WHATSAPP_ORCHESTRATOR_TIMEOUT` default 90s).
- If the orchestrator produced a response → sends it (interactive immediate `:639`, text via
  `send_agent_response.delay` `:668`).
- **If it timed out / errored / produced nothing AND the message wasn't already handled**
  (`:690`), it enqueues `process_message_with_agent` (`:694`) → `AgentService.get_agent_response`
  (`agent_service.py:17`) → **`LangchainService.process_message`** (`:34`), i.e. the old manual
  agentic loop. So the legacy brain is a live fallback, not merely a test endpoint.

### 3.7 Other live entry points into the legacy path

- `process_instagram_dm` (`instagram/tasks.py:12`) and `process_messenger_dm`
  (`messaging/tasks.py:12`) call `AgentService.get_agent_response` directly → **LangchainService**,
  bypassing UnifiedService and LangGraph entirely. Instagram/Messenger bots do NOT use the
  LangGraph path at all.
- `AgentViewSet.process` (`agents/views.py:~106`, `POST /api/agents/{id}/process/`) → also
  legacy LangchainService. Does not create `AgentConversation`, so session memory is lost between
  calls.

### 3.8 Memory, conversation, handover

- **Redis chat memory**: `RedisChatMessageHistory`, key `agent_{agent.id}_{session_id}`,
  TTL `agent.memory_ttl` (`langchain_service.py:165`). Written by both LangGraph (`:98`) and
  legacy (`~:1675`).
- **`AgentConversation`** (apps/agents models): persists `session_id` ↔ phone so the next inbound
  message reuses the same Redis memory (UnifiedService `:598-632`).
- **`Conversation`** (`apps/conversations/models.py:9`): unified inbox row across channels; field
  `mode` ∈ {auto, human, hybrid} gates automation; OneToOne `handover`.
- **Handover** (`apps/handover/models.py:34` `ConversationHandover`): `transfer_to_bot` (:86) /
  `transfer_to_human` (:109), logs `HandoverLog`, notifies via WebSocket. Triggered from
  UnifiedService when the dead-end counter ≥ 3 unknown intents → `IntentType.HUMAN_HANDOFF`.

---

## 4. Communication map (full happy path, file:line)

See the ASCII diagram in §0. Hop-by-hop:

1. Meta → `POST /webhooks/v1/whatsapp/` → `dispatcher.py:54`.
2. HMAC `dispatcher.py:314` → WebhookEvent `dispatcher.py:148` → handler `dispatcher.py:160`.
3. `handlers/whatsapp_handler.py:20` → `WebhookService.process_webhook` → `process_webhook_event.delay` (`whatsapp/tasks/__init__.py:39`).
4. Task → `WebhookService.process_event` (`webhook_service.py:326`) → `post_process_inbound_message` (`:372`).
5. Threaded run of `LLMOrchestratorService.process_message` (`webhook_service.py:592/598` → `unified_service.py:655`).
6. Pipeline → `_call_llm` (`unified_service.py:542`) → `LangGraphService.process_message` (`langgraph_service.py:42`).
7. Graph (`graph.py:31`): `load_context`→`sondagem`→`agent`⇄`execute_tools`→`extract_response`.
8. Response returns; `webhook_service.py:639` (interactive) or `:668` (`send_agent_response.delay`).
9. `send_agent_response` (`whatsapp/tasks/__init__.py:213`) → `WhatsAppAPIService.send_text_message` → `_make_request` (`whatsapp_api_service.py:46`) → Meta Graph API.
10. `MessageService._update_message_sent` broadcasts status over WebSocket (`broadcast_service.py:42`); dashboards also poll SSE (`sse_views.py:374`).

---

## 5. Duplicate apps — which is live

Verified against `config/settings/base.py` INSTALLED_APPS (lines 57-71) and `config/urls.py`.

| Pair | LIVE | DEAD | Evidence |
|---|---|---|---|
| messaging vs messaging_v2 | **`apps.messaging`** (base.py:69, urls.py:88) | `messaging_v2` | `messaging_v2` not in INSTALLED_APPS, 0 imports, no URL include |
| marketing vs marketing_v2 | **`apps.marketing`** (base.py:67, urls.py:102) | `marketing_v2` | `marketing_v2` not in INSTALLED_APPS, 0 imports |
| core vs core_v2 | **`apps.core`** (base.py:57) | `core_v2` | `core_v2` not in INSTALLED_APPS; only a `migrations/` dir, no live code |

`apps.messaging` is the live Messenger dispatcher and also exposes the generic
`MessageDispatcher` (`apps/messaging/dispatcher.py:53`) with whatsapp/email/instagram providers.
The `*_v2` directories are abandoned scaffolds and safe to delete after a final `grep` confirms no
dynamic imports.

---

## 6. Mess / tech-debt — explicit list

1. **Three dead `*_v2` apps** (`messaging_v2`, `marketing_v2`, `core_v2`) — not installed, not
   imported. Pure cruft (§5).

2. **Half-migrated LLM brain.** Production uses `UnifiedService → LangGraphService → graph`, but
   LangGraphService is a wrapper that **reuses LangchainService** for LLM/tools/context/memory.
   LangchainService's own `process_message` manual agentic loop (`:1607`) and
   `_build_dynamic_context` (`:666`) are legacy but **still reachable**.

3. **Legacy loop is a LIVE fallback, not just a test endpoint.** `webhook_service.py:690` enqueues
   `process_message_with_agent` → `AgentService` → `LangchainService.process_message` whenever the
   orchestrator times out / errors. The migration is not isolatable until this fallback is rewired.

4. **Instagram & Messenger bots never use LangGraph.** `process_instagram_dm` and
   `process_messenger_dm` call `AgentService.get_agent_response` (legacy LangchainService) directly,
   bypassing UnifiedService entirely. So "the bot" behaves differently per channel.

5. **`/api/agents/{id}/process/`** (`agents/views.py:~106`) uses legacy LangchainService and creates
   no `AgentConversation` → no session memory. Inconsistent with the WhatsApp path.

6. **Guardrail divergence.** Tool-narrowing `_resolve_allowed_tools` (`langchain_service.py:~593`)
   runs only in the legacy path; LangGraph relies on prompt instructions + an ad-hoc
   `buscar_produto` block in `execute_tools` (`nodes.py:374`). Same guardrail expressed two
   different ways in two places → drift risk.

7. **Context built twice, differently.** Legacy: monolithic `_build_dynamic_context`. LangGraph:
   piecemeal `_catalog_summary` / `_delivery_summary` / `_load_knowledge_context` in `nodes.py`.
   Behavior can silently diverge between the two paths.

8. **Orchestrator runs in a thread with a join-timeout** (`webhook_service.py:617`). The daemon
   thread is not cancelled on timeout — it keeps running (and may still hit the LLM / write Redis)
   while the fallback path also fires. Possible double-processing / double-send risk under slow LLM.

9. **`process_message_stream`** (`langchain_service.py:1746`) has no live caller — dead code.

10. **Deprecated automation tasks** still present: `automation/tasks/__init__.py:46/97`.

11. **Two real-time stacks** (Channels WebSocket + polling SSE). Intentional fallback per
    `CLAUDE.md`, but the SSE views are full DB-polling duplicates of the WebSocket broadcasts.

12. **Possible missing import**: one Explore pass flagged `timezone` usage near
    `unified_service.py:264` without an obvious import. Verify before relying on that branch.
    *(Not confirmed by direct read — treat as a TODO to check.)*

---

## 7. Executive summary (15 lines)

1. Three abandoned apps — `messaging_v2`, `marketing_v2`, `core_v2` — are NOT in INSTALLED_APPS and have zero imports; pure dead weight, deletable.
2. Live LLM path: WhatsApp inbound → `UnifiedService.process_message` (`unified_service.py:655`) → `_call_llm` (`:542`) → `LangGraphService` (`langgraph_service.py:42`) → graph (`graph.py:31`).
3. `LangGraphService` is a thin wrapper that REUSES `LangchainService` for LLM, tools, customer-context and Redis memory — so LangchainService is NOT dead, only its agentic loop is legacy.
4. The Langchain→LangGraph migration is roughly half done: the graph runs, but the old manual while-loop (`langchain_service.py:1607`) is still reachable.
5. Critical: the legacy loop is a LIVE FALLBACK — `webhook_service.py:690` calls `process_message_with_agent` → `AgentService` → `LangchainService.process_message` whenever the orchestrator times out/errors.
6. Instagram and Messenger bots bypass LangGraph entirely and call legacy `AgentService.get_agent_response` directly (`instagram/tasks.py:12`, `messaging/tasks.py:12`).
7. `POST /api/agents/{id}/process/` also uses legacy LangchainService and creates no `AgentConversation`, losing session memory.
8. Guardrails diverge between paths: `_resolve_allowed_tools` (legacy only) vs prompt + ad-hoc block in `nodes.py:374`.
9. Context is built two different ways (`_build_dynamic_context` vs piecemeal node summaries), risking behavioral drift.
10. Outbound WhatsApp all funnels through `whatsapp_api_service.py:46` (Meta Graph API); email via Resend (`email_marketing_service.py:297`); push via pywebpush (`notification_service.py:274`).
11. 24 Celery beat tasks across queues whatsapp/agents/automation/campaigns/default; ~15 of them actually send messages.
12. UnifiedService runs in a daemon thread with a join-timeout (`webhook_service.py:617`) that does not cancel the thread — possible double-processing under slow LLM.
13. Two deprecated automation tasks and one dead method (`process_message_stream`) remain in the tree.
14. Session memory persistence (Redis key `agent_{id}_{session}` + `AgentConversation`) is correct in the WhatsApp/LangGraph path but absent in the direct-API and IG/Messenger paths.
15. WebSocket (Channels) is the primary real-time channel; SSE views are intentional polling fallbacks — duplicate machinery but not dead.
