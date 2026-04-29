# Agent Profiles — Pastita / Ce Saladas Platform

Persistent agent roles for recurring Codex and Claude sessions. Use these profiles when the work needs dedicated review across backend, database/model architecture, frontends, mobile, bot pipeline, or cross-project orchestration.

These are operating profiles, not runtime services. They define what each agent should inspect, what decisions they own, and what output they must produce before code is changed.

## How To Use

For Codex, paste or reference the relevant profile name and file path in the prompt:

```text
Use server2/docs/agents/server2-backend-general.md as your role for this task.
```

For Claude Code, the matching subagent definitions live in:

```text
server2/.claude/agents/
```

Start every agent with a read-only audit unless the task explicitly asks for implementation. All agents must protect the dirty worktree: do not revert unrelated changes and do not delete compatibility paths without a migration plan.

## Agents

| Agent | Claude Code wrapper | Profile doc | Scope |
|---|---|---|---|
| `server2-backend-general` | `.claude/agents/server2-backend-general.md` | `docs/agents/server2-backend-general.md` | Django/DRF/Celery/WhatsApp/checkout/delivery backend |
| `server2-database-models` | `.claude/agents/server2-database-models.md` | `docs/agents/server2-database-models.md` | PostgreSQL, migrations, constraints, tenant boundaries |
| `pastita-frontend-contracts` | `.claude/agents/pastita-frontend-contracts.md` | `docs/agents/pastita-frontend-contracts.md` | API contracts across all frontends vs server2 |
| `pastita-platform-orchestrator` | `.claude/agents/pastita-platform-orchestrator.md` | `docs/agents/pastita-platform-orchestrator.md` | Cross-project architecture, sequencing, release risk |
| `ce-saladas-flutter` | `.claude/agents/ce-saladas-flutter.md` | `docs/agents/ce-saladas-flutter.md` | Flutter mobile app, design system, providers, APK |
| `pastita-dash` | `.claude/agents/pastita-dash.md` | `docs/agents/pastita-dash.md` | React/TS admin dashboard, inbox, handover, uploads |
| `whatsapp-bot` | `.claude/agents/whatsapp-bot.md` | `docs/agents/whatsapp-bot.md` | WhatsApp pipeline, Caio LLM, intent handlers, guards |

## Shared Ground Rules

- Treat `server2` as the canonical backend.
- Treat `Store` as the tenant root unless a review proves otherwise.
- Preserve public contracts used by `ce-saladas`, `ce-saladas-flutter`, and `pastita-dash`.
- Prefer central services over duplicated endpoint logic.
- Do not remove legacy aliases until every known consumer is mapped and a compatibility test exists.
- Findings must include file paths, line references when available, risk level, and a proposed safe cut.
- Implementation plans must separate quick bug fixes from structural refactors.

## Current Platform State (2026-04-28)

### Production (deployed 2026-04-27)
- PIX payment response: interactive button template (code + copy button). No prose.
- `confirmar pedido` → TRACK_ORDER (not CREATE_ORDER).
- TrackOrderHandler: multi-variant phone lookup + order number from message text.
- Distributed webhook lock (Redis) prevents duplicate processing.
- Agent guards: max_iterations reduced, tools restricted per intent, direct reply bypasses LLM.

### Highest Priority Pending
- P0: Mercado Pago central webhook route fix (`apps/webhooks/handlers/mercadopago_handler.py` imports broken service).
- P0: Flutter checkout not yet connected to server2 real endpoint.
- P0: Salada personalizada needs backend contract (persistent order item).
- P1: Frontend contract matrix — map all endpoints consumed by each frontend.
- P1: CheckoutService canonicalization — WhatsApp order flow must call same factory as storefront.
- P1: DB constraints — order_number uniqueness, active cart uniqueness, stock concurrency.

### Key Documents
- `docs/agents/AUDIT_DUPLICATION_CLEANUP_2026-04-28.md` — full architecture audit
- `docs/agents/IMPLEMENTATION_PRIORITY_ROADMAP_2026-04-28.md` — P0→P6 execution plan
- `/home/graco/WORK/PASTITA_ESTADO_PLANEJAMENTO_2026-04-24.md` — consolidated platform state
- `docs/CONTRATOS_CRITICOS_2026-04-24.md` — critical API contracts
