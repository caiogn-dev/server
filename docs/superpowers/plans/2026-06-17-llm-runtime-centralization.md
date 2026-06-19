# LLM/Bot Runtime Centralization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill the legacy Langchain brain, unify all channels on the LangGraph path, and extract the shared LLM logic from the `LangchainService` god-class into a clean `apps/agents/runtime/` package — with zero regression on the WhatsApp revenue flow.

**Architecture:** Strangler migration. Extract shared helpers into focused `runtime/*` modules behind stable interfaces; prove each extraction is behavior-identical with a differential harness BEFORE deleting the legacy source; repoint every caller to one entry point (`AgentRuntime` via `UnifiedService`); delete the legacy loop + dead code last.

**Tech Stack:** Django 5.2, DRF, Celery, LangGraph, langchain-core, Redis, Postgres (via pgbouncer). Tests run inside the `pastita_web` container: `docker cp <file> pastita_web:/app/<file>` then `docker exec -e DJANGO_SETTINGS_MODULE=config.settings.development pastita_web python -m pytest <path>`.

## Global Constraints

- ZERO behavior change on the WhatsApp live path until a step is explicitly a "FIX" — every extraction is byte-identical, proven by differential harness.
- Never delete legacy code while any caller still references it — `grep -rn <symbol> apps` must be empty first.
- Tests must NOT run in parallel against the shared Postgres test DB — run sequentially.
- Baked image: changes activate only at the user's `deploy.sh`. Do not run `migrate` against prod; create migrations only. New indexes/large-table migrations use `AddIndexConcurrently` + `atomic=False`.
- Source-of-truth spec: `docs/superpowers/specs/2026-06-17-llm-runtime-centralization-design.md`.
- Canonical shared helpers to PRESERVE (move, don't rewrite): `_create_llm`, `_create_redis_client`, `_build_customer_context`, `_get_store_for_context`, `_build_tools`, `_get_pending_pix_payment`, `_get_memory`.
- Commit messages in Portuguese.

---

## File Structure (target)

- Create `apps/agents/runtime/__init__.py` — package, exports `AgentRuntime`.
- Create `apps/agents/runtime/factory.py` — LLM + Redis client creation, provider/base-url resolution.
- Create `apps/agents/runtime/context.py` — single context builder (customer, store, menu, delivery, knowledge, cart/PIX/last-order).
- Create `apps/agents/runtime/prompts.py` — system prompt assembly (honors agent.system_prompt), intent prompt.
- Create `apps/agents/runtime/tools.py` — 11 tools + tool-gate + execution helpers.
- Create `apps/agents/runtime/memory.py` — Redis history + AgentConversation persistence helper.
- Create `apps/agents/runtime/service.py` — `AgentRuntime` entry point.
- Modify `apps/agents/graph/nodes.py` — consume runtime modules.
- Modify `apps/agents/services/langgraph_service.py` — thin shim over `AgentRuntime` (or fold in).
- Modify `apps/automation/services/unified_service.py` — call `AgentRuntime`.
- Modify callers: `apps/instagram/tasks.py`, `apps/messaging/tasks.py`, `apps/whatsapp/services/webhook_service.py`, `apps/agents/views.py`.
- Delete (last): legacy methods in `apps/agents/services/langchain_service.py`, `apps/agents/services/agent_service.py` (get_agent_response), `apps/automation/services/flow_executor.py`, dead handlers/tasks.

---

## Task 1: Differential harness scaffold + factory module

**Files:**
- Create: `apps/agents/runtime/__init__.py`, `apps/agents/runtime/factory.py`
- Test: `apps/agents/runtime/tests/__init__.py`, `apps/agents/runtime/tests/test_factory_parity.py`
- Source ref: `apps/agents/services/langchain_service.py:43-163` (`_create_redis_client`, `_create_llm`, env/base-url maps)

**Interfaces:**
- Produces: `factory.create_llm(agent) -> BaseChatModel`, `factory.create_redis_client() -> redis.Redis`, `factory.get_llm(agent) -> BaseChatModel` (cached by `agent.id` + config hash).

- [ ] **Step 1: Parity test** — capture `LangchainService(agent)._create_llm` config (provider, model, base_url, temperature, max_tokens, timeout) for 3 agents (openai/anthropic/nvidia fixtures via SimpleNamespace) and assert `factory.create_llm(agent)` produces a client with identical `.model_name`/`.temperature`/`.openai_api_base` (or anthropic equivalent). Mock network; do NOT call the LLM.
- [ ] **Step 2: Run, verify FAIL** — `pytest apps/agents/runtime/tests/test_factory_parity.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement factory** — move `_create_llm`/`_create_redis_client` bodies + the env-key map (`:53`) and base-url map (`:66`) and suffix stripper (`:81`) verbatim into `factory.py` as module functions. Add `get_llm(agent)` with an `lru_cache`-style dict keyed by `(agent.id, provider, model, base_url)`.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git add apps/agents/runtime/ && git commit -m "feat(runtime): extrai factory de LLM/Redis com paridade provada"`

## Task 2: memory module

**Files:**
- Create: `apps/agents/runtime/memory.py`
- Test: `apps/agents/runtime/tests/test_memory_parity.py`
- Source ref: `langchain_service.py:165` (`_get_memory`), `langgraph_service.py:61,98` (load/save), `unified_service.py:564-632` (AgentConversation persistence)

**Interfaces:**
- Consumes: `factory.create_redis_client`.
- Produces: `memory.get_history(agent, session_id) -> RedisChatMessageHistory`, `memory.load_tail(agent, session_id, n) -> list`, `memory.save_turn(agent, session_id, user_text, ai_text)`, `memory.persist_agent_conversation(agent, phone, session_id) -> AgentConversation`.

- [ ] **Step 1: Parity test** — assert `memory.get_history(agent, sid)` returns the same Redis key (`agent_{id}_{sid}`) and TTL as `LangchainService._get_memory`. Mock Redis.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — move `_get_memory` verbatim; implement `load_tail`/`save_turn` as the single version (collapsing the two open-coded copies); move the `AgentConversation` get/update_or_create from `unified_service.py:564-632` into `persist_agent_conversation`.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): extrai memory (history + AgentConversation) com paridade"`

## Task 3: tools module

**Files:**
- Create: `apps/agents/runtime/tools.py`
- Test: `apps/agents/runtime/tests/test_tools_parity.py`
- Source ref: `langchain_service.py:997-1427` (`_build_tools`), `:609` (`_get_pending_pix_payment`), `:593` (`_resolve_allowed_tools`), `nodes.py:339-391` (graph exec loop, confirmation guard, safe-error)

**Interfaces:**
- Consumes: `factory`, `memory`.
- Produces: `tools.build_tools(agent, phone_number, store) -> list[Tool]`, `tools.resolve_allowed(intent, all_tools) -> list[Tool]`, `tools.get_pending_pix_payment(...)`.

- [ ] **Step 1: Parity test** — assert `tools.build_tools(agent, phone, store)` returns the same 11 tool `.name`s in the same order as `LangchainService._build_tools`. Build a SimpleNamespace store; mock DB-touching tool internals.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — move `_build_tools` (all 11 closures) + `_get_pending_pix_payment` + `_resolve_allowed_tools` verbatim. Keep tool bodies identical.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): extrai tools (11 + tool-gate) com paridade"`

## Task 4: context module (extract shared + dedupe menu/delivery)

**Files:**
- Create: `apps/agents/runtime/context.py`
- Test: `apps/agents/runtime/tests/test_context_parity.py`
- Source ref: `langchain_service.py:339` (`_build_customer_context`), `:1429` (`_get_store_for_context`); `nodes.py:238/294/269` (`_catalog_summary`/`_delivery_summary`/`_load_knowledge_context`)

**Interfaces:**
- Consumes: nothing from runtime (pure builders + DB).
- Produces: `context.customer(agent, phone, conversation_id, store)`, `context.resolve_store(agent, conversation_id)`, `context.catalog(store)`, `context.delivery(store)`, `context.knowledge(agent, store)`.

- [ ] **Step 1: Differential harness** — for a real store (ce-saladas) capture `_build_customer_context` and `_get_store_for_context` outputs (legacy) vs `context.customer`/`context.resolve_store` (new); assert identical strings. Run via `docker exec` against the live container DB (read-only).
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — move `_build_customer_context`, `_get_store_for_context` verbatim; move `_catalog_summary`/`_delivery_summary`/`_load_knowledge_context` from nodes.py into `context.py` as the single menu/delivery/knowledge builders.
- [ ] **Step 4: Run harness, verify IDENTICAL output.**
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): extrai context (customer/store/menu/delivery/knowledge) com diff idêntico"`

## Task 5: PORT cart/PIX/last-order context from legacy into context module

**Files:**
- Modify: `apps/agents/runtime/context.py`
- Test: `apps/agents/runtime/tests/test_context_session.py`
- Source ref: `langchain_service.py:852-984` (session/cart/PIX/last-order block inside `_build_dynamic_context`)

**Interfaces:**
- Produces: `context.session_state(agent, phone, store) -> str` (cart items, pending delivery method/address/fee, waiting_for_address, last_order, PIX guardrails).

- [ ] **Step 1: Characterization test** — build a CustomerSession with cart_data (pending_items, delivery_fee, last_order) and assert `context.session_state(...)` reproduces the exact text the legacy block produced (copy expected strings from `:852-984`).
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — port the `:852-984` logic verbatim into `context.session_state`.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): porta estado de carrinho/PIX/último-pedido p/ o context (paridade com legado)"`

## Task 6: prompts module (+ FIX: honor agent.system_prompt, persona_name field)

**Files:**
- Create: `apps/agents/runtime/prompts.py`
- Modify: `apps/agents/models.py` (add `persona_name`), create migration
- Test: `apps/agents/runtime/tests/test_prompts.py`
- Source ref: `nodes.py:88-189` (`_SYSTEM_TEMPLATE`, `_build_system_prompt`), `detector.py:271` (intent prompt)

**Interfaces:**
- Consumes: `context`.
- Produces: `prompts.system_prompt(agent, store, customer_ctx, knowledge_ctx, session_ctx) -> str` (merges `agent.system_prompt`/`context_prompt`), `prompts.intent_prompt() -> str`.

- [ ] **Step 1: Tests** — (a) `system_prompt` includes `agent.system_prompt` text when set (the FIX); (b) `persona_name` field exists and defaults blank, prompt uses it when set else `agent.name`.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — move `_SYSTEM_TEMPLATE`/`_build_system_prompt`; add merge of `agent.system_prompt`; add `persona_name = models.CharField(max_length=80, blank=True, default='')` to Agent; `makemigrations agents`; move intent prompt from detector.py.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): prompts unificados (honra system_prompt) + campo persona_name"`

## Task 7: AgentRuntime service + repoint graph/LangGraphService

**Files:**
- Create: `apps/agents/runtime/service.py`
- Modify: `apps/agents/graph/nodes.py` (consume runtime.context/tools/prompts), `apps/agents/services/langgraph_service.py` (delegate to AgentRuntime)
- Test: `apps/agents/runtime/tests/test_runtime_smoke.py`

**Interfaces:**
- Consumes: factory, context, prompts, tools, memory, graph.
- Produces: `AgentRuntime(agent).process_message(message, session_id, phone_number, conversation_id) -> dict` (same return shape as `LangGraphService.process_message`).

- [ ] **Step 1: Smoke/parity test** — with a mocked LLM returning a fixed reply, assert `AgentRuntime(agent).process_message(...)` returns the same dict shape/keys as `LangGraphService.process_message`.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — `AgentRuntime` wires factory→graph using runtime modules; nodes.py imports from runtime instead of inline; cache compiled graph per `agent.id`. `LangGraphService` becomes a thin shim calling `AgentRuntime` (keep its public method names for back-comat: process_message/get_conversation_history/clear_memory).
- [ ] **Step 4: Run, verify PASS + existing whatsapp tests green** (`pytest apps/whatsapp/tests/`).
- [ ] **Step 5: Commit** — `git commit -am "feat(runtime): AgentRuntime como entrada única; grafo consome módulos runtime"`

## Task 8: Repoint UnifiedService + all channel callers to AgentRuntime

**Files:**
- Modify: `apps/automation/services/unified_service.py:561`, `apps/instagram/tasks.py:13/41`, `apps/messaging/tasks.py:13/41`, `apps/agents/views.py` (process/history/clear_memory)
- Test: `apps/agents/runtime/tests/test_callers_repoint.py`

**Interfaces:**
- Consumes: `AgentRuntime`.

- [ ] **Step 1: Test** — assert IG/Messenger tasks now go through `UnifiedService.process_message` (mock it, assert called) instead of `AgentService.get_agent_response`.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — `unified_service._call_llm` uses `AgentRuntime`; IG/Messenger tasks call `UnifiedService(...).process_message(...)`; `agents/views.py` process → `AgentRuntime` (creates AgentConversation), history/clear_memory → `memory` module.
- [ ] **Step 4: Run, verify PASS + `grep -rn "AgentService.get_agent_response\|LangchainService(" apps` shows only webhook fallback + legacy file.**
- [ ] **Step 5: Commit** — `git commit -am "refactor: IG/Messenger/REST/Unified repontados p/ AgentRuntime"`

## Task 9: FIX double-send — collapse fallback + daemon thread into one guarded path

**Files:**
- Modify: `apps/whatsapp/services/webhook_service.py:657-795`
- Test: `apps/whatsapp/tests/test_orchestrator_single_path.py`

- [ ] **Step 1: Test** — simulate orchestrator timeout; assert the fallback does NOT also send when the orchestrator eventually completes (single-send guarded by an atomic Redis flag set before the LLM call).
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — gate the fallback on a Redis `processed:{message_id}` flag set atomically (`SET NX`) before dispatch; if set, fallback no-ops. Bound the LLM via client timeout instead of relying solely on the un-cancellable thread join.
- [ ] **Step 4: Run, verify PASS + whatsapp tests green.**
- [ ] **Step 5: Commit** — `git commit -am "fix(whatsapp): caminho único guardado — elimina risco de resposta dupla"`

## Task 10: DELETE legacy brain + dead code (only after grep is clean)

**Files:**
- Modify: `apps/agents/services/langchain_service.py` (remove `process_message`, `process_message_stream`, `_build_dynamic_context`, duplicate menu/delivery/CONDUTA blocks; keep nothing legacy-only)
- Modify: `apps/agents/services/agent_service.py` (remove `get_agent_response`; keep `create_order_from_conversation`)
- Delete: `apps/automation/services/flow_executor.py`; remove `AgentFlow`/`FlowSession`/`FlowExecutionLog` + 501 stub
- Delete: `ProductNotFoundHandler` (catalog.py:276); dead `legacy_tasks.py` funcs (move `process_pending_webhook_events`/`retry_failed_webhook_events` out first); deprecated delegators
- Test: full whatsapp + agents suites

- [ ] **Step 1: Pre-delete grep** — `grep -rn "process_message_stream\|_build_dynamic_context\|get_agent_response\|FlowExecutor\|ProductNotFoundHandler" apps` → confirm only definitions remain (no callers). If any caller remains, STOP and repoint it.
- [ ] **Step 2: Move live webhook tasks** out of `legacy_tasks.py` into `apps/whatsapp/tasks/webhook_tasks.py`; update Beat refs in `config/celery.py`.
- [ ] **Step 3: Delete** the legacy symbols/files listed above. Make migration for removed models (`AgentFlow` etc.).
- [ ] **Step 4: Run full suites** — `pytest apps/agents apps/whatsapp -q` → green; `python manage.py check` → no issues; `makemigrations --check`.
- [ ] **Step 5: Commit** — `git commit -am "refactor: remove cérebro Langchain legado + FlowExecutor + código morto"`

## Task 11: Perf FIXes — cache + LLM out of transaction

**Files:**
- Modify: `apps/agents/runtime/service.py` (graph/LLM cache already in Task 7 — verify), `apps/agents/runtime/context.py` (cache store/menu/knowledge per store.id TTL), `apps/whatsapp/services/webhook_service.py` (LLM call outside `@transaction.atomic`)
- Test: `apps/agents/runtime/tests/test_context_cache.py`

- [ ] **Step 1: Test** — assert `context.catalog(store)` second call within TTL issues 0 queries (CaptureQueriesContext), and busts on catalog change signal.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** — wrap catalog/delivery/knowledge in `cache.get_or_set` keyed by `store.id` + TTL (5-15 min) with signal-based invalidation on product/category save; ensure the orchestrator LLM call is not inside an open DB transaction.
- [ ] **Step 4: Run, verify PASS + whatsapp tests green.**
- [ ] **Step 5: Commit** — `git commit -am "perf(runtime): cache de contexto por loja + LLM fora da transação"`

---

## Self-Review

- **Spec coverage:** KEEP (Tasks 1-7), PORT cart/PIX (Task 5), REPOINT (Task 8), FIX double-send (Task 9) + system_prompt/persona (Task 6) + cache/transaction (Task 11), DELETE (Task 10). FlowExecutor delete (Task 10). persona_name field (Task 6). All spec sections mapped.
- **Placeholder scan:** every task names exact files, exact source line refs to move, and a concrete verification command. No "TBD"/"handle edge cases".
- **Ordering safety:** deletions (Task 10) gated on a grep-clean precondition; extractions proven identical before any delete.
- **Type consistency:** `AgentRuntime.process_message` return shape pinned to `LangGraphService.process_message` (Task 7); `LangGraphService` kept as shim so existing callers' method names survive until Task 8 repoints them.
