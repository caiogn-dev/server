# EVOLUCAO_SERVER.md — Backlog & Histórico do backend `server`

> Atualizado em: 2026-06-30
> Branch trunk: `development` (NUNCA `main` — congelada desde 29/mai)

---

## PRs Abertos (não mergeados em `development`)

| PR | Título | Prioridade |
|----|--------|------------|
| #282 | fix(lgpd): mascara telefones e credenciais em logs — 7 arquivos | P0 |
| #281 | fix(seguranca): NameError + IDOR no export de conversas do audit | P0 |

---

## Histórico de Fixes (já em `development`)

| Commit | Fix |
|--------|-----|
| `0f871b4` | feat(webhooks): endpoint de diagnóstico WhatsApp completo |
| `5db9e3f` | fix(seguranca): IDOR em calculate_fee de entrega (P0) + sanitiza PII-placeholder |
| `a95a896` | fix(seguranca): IDOR is_staff no Instagram (P0) + IDOR em cupom (P1) |
| `7f9a841` | feat(pagamento): link de pagamento real no avulso |
| `e3c0519` | fix(seguranca): criptografa page_access_token/app_secret do Messenger |
| `fb7d075` | fix(seguranca): valida URL de webhook contra SSRF |
| `1a64db6` | fix(seguranca): escopa store_data/create do CompanyProfile (IDOR) |
| `b7facfc` | fix(seguranca): escopa handover por tenant (IDOR) |
| `239d881` | fix(seguranca): escopa endpoints de Marketing (IDOR) |
| `f3d6e21` | fix(seguranca): escopa actions de Campaigns (IDOR) |
| `9c7b2fa` | fix(seguranca): valida ownership de account/company em relatórios |
| `7a8e028` | fix(seguranca): verifica acesso no subscribe_conversation dos WS (IDOR) |
| `1d7e1ad` | fix(seguranca): valida ownership da conta nas actions send_* WhatsApp |

---

## Sessão 2026-06-30 — Fix atual nesta branch

**Problema**: `StoreComboViewSet` e `StoreProductTypeViewSet` registrados no router plano
(`GET /api/v1/stores/combos/` e `GET /api/v1/stores/product-types/`) retornavam
`objects.all()` quando nenhum parâmetro de loja era fornecido — expondo dados de todos
os tenants a qualquer usuário autenticado. IDOR cross-tenant.

**Fix**: `else` branch adicionado em `get_queryset()` de ambos os ViewSets:
- Sem escopo + anônimo → `queryset.none()`
- Sem escopo + autenticado não-superuser → filtra por `accessible_store_ids(user)`
- Superuser → visão global mantida (cross-tenant intencional)

Quando `?store=<slug>` ou `store_slug` via URL aninhada está presente, o comportamento
anterior é preservado (sem impacto no dashboard nem no storefront público via `public_api`).

---

## Backlog Priorizado (próximas sessões)

### P0 — Segurança crítica

1. **timing-attack em comparação de tokens** — `webhooks.py:387,657`,
   `whatsapp/webhooks/views.py:67`, `messaging/api/views.py:390`,
   `whatsapp/services/webhook_service.py:45`: todas usam `==` em vez de
   `hmac.compare_digest()` para verificar `verify_token` e `access_token`.
   Risco real baixo (256-bit token + jitter de rede), mas trivial de corrigir.

2. **`str(e)` exposto ao cliente** — `company_profile_views.py:168`:
   `Response({'error': str(e)})` vaza mensagens internas de exceção.

### P1 — Bugs de fluxo

3. **Testes de regressão críticos ausentes**: OTP, delivery zones, route calculation,
   checkout payload, orders by token, agent guardrails (citados no CLAUDE.md como
   `Critical pending work #3`).

4. **Namespace mobile para pedidos**: criar/verificar namespace limpo
   `/api/v1/mobile/` para detail/status/tracking/reorder sem conflito com rotas
   administrativas (citado no CLAUDE.md como `Critical pending work #1`).

### P2 — Performance

5. **N+1 em `CustomerOrdersView`** — `order.items.count()` dentro de loop (linha 614
   de `webhooks.py`). O `Count` via `annotate` é aplicado, mas o slice `[:3]` ainda
   itera os items sem o prefetch completo.

### P3 — Limpeza

6. **TODO de combo_items** em `CustomerOrdersView` (linha 611-613) — comentado mas
   nunca implementado. Avaliar se o modelo `StoreOrder.combo_items` existe.
