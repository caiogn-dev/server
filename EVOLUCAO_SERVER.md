# Evolução do Backend server (Cardapidex/Pastita)

Documento de rastreamento do loop diário de evolução. Mantido pelo bot de revisão automática.
Branch trunk: `development`. Branch `main` congelada desde 29/mai/2026.

---

## Histórico de execuções

### 2026-06-28

**Baseline de testes:** Ambiente de checkout limpo sem Docker (sem PostgreSQL/Redis).
Suíte completa não executável neste container; testes que usam migrações PostgreSQL-específicas
(add_index concurrently) falham por design. Isso é pré-existente, não regressão.

**Bug encontrado e corrigido:** `apps/audit/api/views.py` linha 140 — `NameError` em produção

- **Tipo:** P0 — Bug de runtime + IDOR potencial
- **Descrição:** O branch `conversations` do `ExportViewSet.export()` chamava `_accessible_accounts()`
  que **não existe e não está importada** no módulo. Causa `NameError` em produção sempre que
  qualquer usuário tenta exportar conversas. Adicionalmente, se a função fosse resolvida de outro
  escopo acidentalmente, poderia retornar dados cross-tenant (IDOR).
- **Correção:** Substituído por `accessible_whatsapp_account_ids(user)` que já estava importada
  na linha 15 e retorna exatamente o mesmo conjunto de IDs, corretamente escopados por tenant.
- **PR:** `bot/server-2026-06-28-audit-export-idor`

**Outros achados (backlog para próximas execuções):**

| Prioridade | Arquivo | Linha | Problema |
|---|---|---|---|
| P0 | apps/core/auth/views.py | 76 | PII em log — telefone em texto plano |
| P0 | apps/core/auth/whatsapp_auth.py | 235, 281 | PII em log — telefone |
| P0 | apps/automation/services/session_manager.py | 260, 467, 477, 487 | PII em log — telefone |
| P0 | apps/whatsapp/services/webhook_service.py | 1108, 1442, 1488, 1498 | PII em log — telefone |
| P0 | apps/whatsapp/services/order_service.py | 401 | PII em log — código PIX parcial |
| P0 | apps/campaigns/services/campaign_service.py | 321, 380, 383 | PII em log — telefone |
| P1 | apps/automation/api/views/company_profile_views.py | 92-98 | IDOR — account_id não validado antes de uso |
| P1 | apps/whatsapp/webhooks/views.py | 71 | Credencial (verify_token) em log |
| P2 | apps/mobile_api/urls.py | — | Sem rate limiting em /orders/by-token/ |

---

### 2026-06-30

**Bug encontrado e corrigido:** `StoreComboViewSet` e `StoreProductTypeViewSet` — IDOR cross-tenant

- **Tipo:** P0 — Vazamento de dado cross-tenant
- **Descrição:** Ambos os ViewSets, registrados no router plano
  (`GET /api/v1/stores/combos/` e `GET /api/v1/stores/product-types/`), retornavam
  `objects.all()` quando nenhum parâmetro de loja era fornecido — expondo dados de
  todos os tenants a qualquer usuário autenticado.
- **Correção:** `else` branch adicionado em `get_queryset()` de ambos os ViewSets:
  - Sem escopo + anônimo → `queryset.none()`
  - Sem escopo + autenticado não-superuser → filtra por `accessible_store_ids(user)`
  - Superuser → visão global mantida (cross-tenant intencional)

  Quando `?store=<slug>` ou `store_slug` via URL aninhada está presente, o comportamento
  anterior é preservado (sem impacto no dashboard nem no storefront público via `public_api`).
- **Testes:** `apps/stores/tests/test_combo_product_type_idor.py` (RED→GREEN confirmado)
- **PR:** `bot/server-2026-06-30-idor-combo-product-type`

---

## Próximo passo priorizado

**P0 — timing-attack em comparação de tokens**: `webhooks.py:387,657`,
`whatsapp/webhooks/views.py:67`, `messaging/api/views.py:390`,
`whatsapp/services/webhook_service.py:45` usam `==` em vez de
`hmac.compare_digest()` para verificar `verify_token`/`access_token`.
Risco real baixo (256-bit token + jitter de rede), mas trivial de corrigir.

Outros achados relevantes para as próximas sessões:

1. **`str(e)` exposto ao cliente** — `company_profile_views.py:168`:
   `Response({'error': str(e)})` vaza mensagens internas de exceção.
2. **Testes de regressão críticos ausentes**: OTP, delivery zones, route calculation,
   checkout payload, orders by token, agent guardrails (citados no CLAUDE.md como
   `Critical pending work #3`).
3. **Namespace mobile para pedidos**: criar/verificar namespace limpo
   `/api/v1/mobile/` para detail/status/tracking/reorder sem conflito com rotas
   administrativas (citado no CLAUDE.md como `Critical pending work #1`).
4. **N+1 em `CustomerOrdersView`** — `order.items.count()` dentro de loop (linha 614
   de `webhooks.py`). O `Count` via `annotate` é aplicado, mas o slice `[:3]` ainda
   itera os items sem o prefetch completo.
5. **TODO de combo_items** em `CustomerOrdersView` (linha 611-613) — comentado mas
   nunca implementado. Avaliar se o modelo `StoreOrder.combo_items` existe.
