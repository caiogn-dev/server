# ESTADO — Backend server2 (`caiogn-dev/server`)

> **Fonte única de verdade** do que está FEITO, EM ANDAMENTO e no BACKLOG.
> Todo PR que mexe no backend **atualiza este arquivo no mesmo PR**.
> Loops e sessões: **NÃO** peguem item em `FEITO` nem em `EM ANDAMENTO`. Ao começar
> algo, mova-o para `EM ANDAMENTO` (com data + quem) no mesmo PR — isso "reserva" o item
> e evita dois agentes refazerem a mesma coisa (bug de versão).

**Trunk:** `development` (o deploy sai dele). `main` está **CONGELADA** desde 29/mai — não use.
**Regra dura:** trunk só avança por **PR revisado** (`gh pr create --base development`).
NUNCA `push` direto em `development`/`main`. NUNCA `--force`.

---

## ✅ FEITO — NÃO REFAZER

### SaaS Fase 1 — Loop de cobrança recorrente (2026-06-30, deployado em `development`)
- `apps/stores/services/subscription_lifecycle.py` — `decide_transition`: função **pura** trial→carência→suspensão + dunning (past_due).
- `apps/stores/tasks.py` — Celery `enforce_subscription_lifecycle` (beat 04:00 UTC; `transaction.atomic` + `select_for_update(skip_locked=True)`).
- `apps/stores/billing.py` — `store_accepts_orders` → **403** no checkout do storefront p/ loja suspensa.
- Setup fee one-off (preference MP) **duplamente gated** (`BILLING_SETUP_FEE_ENABLED` + `charges_setup_fee` por plano).
- Webhook `mark_setup_fee_paid` — funciona com payload **cru** `{type, data:{id}}` do MP (busca o payment no token da plataforma).
- Endpoints `subscription/`, `subscription/cancel/`, `subscription/change-plan/` (`subscription_views.py`), gated por `_can_manage` (owner/staff/superuser).
- **Hotfix CRÍTICO já em `development`** (`bd0369d`): guard `is_billing_exempt` em `cancel_subscription` **e** `apply_preapproval_event` (defesa em profundidade).
- Spec/plano: `docs/superpowers/specs/2026-06-29-cardapidex-saas-master-design.md` · `docs/superpowers/plans/2026-06-29-fase1-loop-cobranca-recorrente.md`.

### Kill-switches (estado atual)
- `BILLING_ENFORCEMENT_ENABLED` = **ON** (trial→carência→suspensão rodando).
- `BILLING_SETUP_FEE_ENABLED` = **OFF** · `BILLING_AUTOCHARGE_ENABLED` = **OFF** — **não ligar** (envolve dinheiro real + config externa no painel MP).

### 🔒 INVARIANTE SAGRADO
`billing_exempt=True` curto-circuita **TODA** cobrança/bloqueio. As 3 lojas reais
(`ce-saladas`, `kero-kero`, `pastita`) são isentas e **NUNCA** podem ser cobradas,
suspensas, bloqueadas ou ter a assinatura no MP tocada. Todo código novo que toque
assinatura/cobrança **DEVE** checar `is_billing_exempt` antes de agir.

---

## 🚧 EM ANDAMENTO
- _(vazio — atualize aqui ao reservar um item)_

---

## 📋 BACKLOG (prioridade)
- **P0 segurança contínua:** IDOR / isolamento cross-tenant, HMAC de webhooks, timing attacks, PII/segredos em log, SSRF. (use `is_superuser`, **não** `is_staff`, p/ owner cross-tenant.)
- **P0** bugs de produção · **P1** fluxos quebrados.
- **P1** suporte de backend à **Fase 2** (guiar o lojista / onboarding) — só itens já no roadmap; não inventar escopo.
- **P2** performance (N+1, índices) · **P3** limpeza / código morto.

---

## Convenções
- TDD + zero-regressão: teste **primeiro**, suíte **antes e depois**.
- Multi-tenant: TODO acesso a dados escopado por loja/conta.
- Segredos/tokens nunca em log. Webhooks validam HMAC.
- Commits e PRs **em português**. Só o repo `server` — não toque em outros.
