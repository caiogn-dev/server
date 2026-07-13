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
- **PR:** `bot/server-2026-06-28-audit-export-idor` (aberto, aguardando merge)

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

### 2026-06-29

**Baseline de testes:** 13 testes do módulo `test_pii_log_enforcement` rodados com Django instalado
localmente (sem Docker). Testes de regressão `test_pii_masking` e `test_customer_pii_sanitize`
também passam (13/13). Docker indisponível; suíte de integração não executável.

**Bug encontrado e corrigido:** PII (telefones) em logs — violação de LGPD art. 46

- **Tipo:** P0 — Vazamento de dado pessoal sensível em logs de produção
- **Arquivos corrigidos (7):**
  - `apps/core/auth/views.py:76` — OTP send: `{phone}` → `mask_phone(phone)`
  - `apps/core/auth/whatsapp_auth.py:235,281` — `clean_phone` → `mask_phone(clean_phone)`
  - `apps/automation/services/session_manager.py:260,467,477,487` — `self.phone_number` mascarado
  - `apps/whatsapp/services/webhook_service.py:1108,1442,1488,1498` — `from_number`/`phone_number` mascarados; `contact_name` removido do log
  - `apps/whatsapp/services/order_service.py:33,397,401,405,491,548` — `phone_number` mascarado; `pix_code` não logado mais em claro (8 chars truncados, sem expor código completo)
  - `apps/campaigns/services/campaign_service.py:321,380,383` — `recipient.phone_number` mascarado
  - `apps/whatsapp/webhooks/views.py:71` — `token` de credencial **removido** do log de falha de verificação
- **Testes:** 13 novos casos em `apps/core/tests/test_pii_log_enforcement.py` (RED→GREEN confirmado)
- **PR:** `bot/server-2026-06-29-pii-logs`

---

### 2026-07-01

**Fix:** IDOR via `is_staff` em variantes, combos e product-types — `apps/stores/api/views/product_views.py`
- `StoreProductVariantViewSet.get_queryset:257`, `StoreComboViewSet._assert_store_access:290`, `StoreProductTypeViewSet._assert_store_access:374`
- `is_staff or is_superuser` → `is_superuser` (convenção: is_staff = acesso ao /admin, NÃO cross-tenant)
- **PR:** `bot/server-2026-07-01-idor-variant-combo-write` (mergeado em `c036544`)

---

### 2026-07-02

**Fix:** IDOR via `account_id` em `company_profile_views.py` + info-disclosure via str(e) — P1
- `WhatsAppAccount.objects.get(id=account_id)` sem escopo de tenant → tenant gate inserido
- `Store.DoesNotExist` / `DoesNotExist` agora → 404; str(e) removido de respostas
- **PR:** `bot/server-2026-07-02-store-data-idor-account` (mergeado)

---

### 2026-07-03

**Fix:** Throttle dedicado para endpoints públicos de pedido por token — P2
- `OrderByTokenView` e `PaymentStatusView` passaram a ter `_OrderTokenThrottle` (30/min)
- **PR:** `bot/server-2026-07-03-order-token-throttle` (mergeado)

---

### 2026-07-04

**Fix:** `StoreOrder.generate_order_number` usava `random.choices` (não-CSPRNG) — P2
- Substituído por `secrets.randbelow(10000)` em `apps/stores/models/order.py:336`
- **PR:** `bot/server-2026-07-04-order-number-csprng` (mergeado)

---

### 2026-07-05

**Fix:** IDOR de escrita em serializers — Onda 1 — P1
- `StoreSlugOrIdField.to_internal_value`: tenant gate via `user_can_access_store`
- `StoreDeliveryZoneCreateSerializer.validate_store`: método adicionado com tenant gate
- `StoreOrderCreateSerializer._resolve_store`: `not is_staff` → `not is_superuser`
- **PR:** `bot/server-2026-07-05-serializer-write-idor` (mergeado em `c036544`)

> **AVISO:** Os fixes desta entrada foram **reintroduzidos** por merges de feature branches
> (edição de pedido, Fase 3 pagamentos). Corrigido novamente em 2026-07-13 — PR #301.

---

### 2026-07-06

**Fix:** IDOR de escrita em serializers — Onda 2 — P1
- `StoreIntegrationCreateSerializer`, `StoreWebhookSerializer`, `StorePrintAgentCreateSerializer`
- Padrão: `validate_store` com `user_can_access_store` + `is_superuser` bypass
- **PR:** `bot/server-2026-07-06-serializer-idor-integration-webhook-print` (mergeado)

---

### 2026-07-07

**Fix:** IDOR write em `CreateAgentFlowSerializer` + is_staff bypass em `AutoMessageViewSet` — P1
- `apps/automation/api/serializers.py:564`: `validate_store` adicionado
- `apps/automation/api/views/auto_message_views.py:68`: `is_superuser or is_staff` → `is_superuser`
- **PR:** `bot/server-2026-07-07-idor-agentflow-automessage` (mergeado)

---

### 2026-07-09

**Fix:** info-disclosure via `str(e)` em orders e campaigns — P0
- `apps/orders/views.py`: 3 endpoints Uber (delivery request, status, cancel)
- `apps/campaigns/api/views.py`: `CampaignViewSet.process`, `ContactListViewSet.import_csv`
- **PR:** #297 (`bot/server-2026-07-09-info-disclosure-str-e`) — **aberto, aguardando merge**

---

### 2026-07-10

**Fix:** `is_staff` bypass cross-tenant em agentes e conversas — P1
- `apps/agents/views.py:33,70`: `_accessible_agents` e `_enforce_account_scope`
- `apps/conversations/services/universal_conversation_service.py:165`: `_is_staff()`
- `apps/conversations/api/views.py:314`: `assign_agent`
- Bônus: str(e) info-disclosure em `agents/views.py:process`
- **PR:** #298 (`bot/server-2026-07-10-is-staff-idor-agents-conversations`) — **aberto**

---

### 2026-07-11

**Fix:** info-disclosure via `str(e)` em payments e storefront AllowAny — P0
- `apps/stores/api/payment_views.py`: 6 endpoints autenticados
- `apps/stores/api/views/storefront_views.py`: 4 endpoints AllowAny (cart, checkout, delivery-fee)
- **PR:** #299 (`bot/server-2026-07-11-str-e-payment-storefront`) — **aberto**

---

### 2026-07-12

**Fix:** info-disclosure via `str(e)` em combo (AllowAny), subscription, print-SSE e webhook — P0/P1
- `apps/stores/api/views/combo_views.py`: endpoint AllowAny expunha erros ORM
- `apps/stores/api/views/subscription_views.py`: 3 pontos com SubscriptionError vazando config interna
- `apps/stores/api/views/print_views.py`: str(e) no payload SSE
- `apps/stores/api/webhooks.py`: str(e) na resposta ao Mercado Pago
- **PR:** #300 (`bot/server-2026-07-12-str-e-combo-subscription-print-webhook`) — **aberto**

---

### 2026-07-13

**Baseline de testes:** 11 testes `SimpleTestCase` em `test_serializer_idor_regression.py` passando
(sem Docker/PostgreSQL). Testes SimpleTestCase existentes (`test_delivery_fee_refactor`,
`test_subscription_lifecycle`) sem regressão (37/37).

**Regressão encontrada e corrigida:** 3 tenant gates em serializers sobrescritos por merges — P1

- **Causa raiz:** `373e4c7 (merge: edição de pedido)` e `e4a03bb (merge: Fase 3 pagamentos)`
  foram baseados em snapshots anteriores ao PR #294, reintroduzindo os IDORs de escrita.
- **Método de detecção:** `git diff c036544 HEAD -- apps/stores/api/serializers.py`

| Serializer | Regressão | Fix |
|---|---|---|
| `StoreOrderCreateSerializer._resolve_store` | `not is_staff` (bypass) | `not is_superuser` |
| `StoreSlugOrIdField.to_internal_value` | tenant gate removido + erro vaza UUID | tenant gate + msg genérica |
| `StoreDeliveryZoneCreateSerializer` | `validate_store` removido | restaurado com tenant gate |

- **Testes:** 11 novos casos RED→GREEN
- **PR:** #301 (`bot/server-2026-07-13-serializer-idor-regression`) — **aberto**

---

## PRs abertos aguardando merge (2026-07-13)

| PR | Branch | Descrição | Prioridade |
|---|---|---|---|
| #297 | `bot/server-2026-07-09-info-disclosure-str-e` | str(e) em orders/campaigns | P0 |
| #298 | `bot/server-2026-07-10-is-staff-idor-agents-conversations` | is_staff IDOR em agents/conversations | P1 |
| #299 | `bot/server-2026-07-11-str-e-payment-storefront` | str(e) em payments e storefront AllowAny | P0 |
| #300 | `bot/server-2026-07-12-str-e-combo-subscription-print-webhook` | str(e) em combo/subscription/SSE/webhook | P0/P1 |
| #301 | `bot/server-2026-07-13-serializer-idor-regression` | Regressão IDOR em 3 serializers | P1 |

---

## Próximo passo priorizado

1. **URGENTE — Merges evitando regressões:** ao mergearem PRs de feature, garantir que
   não sobrescrevem fixes de segurança. Estratégia: rebasear feature branches em `development`
   ANTES de abrir PR, não depois do bot ter mergeado fixes.

2. **P1 — Sweep restante de is_staff:** `apps/agents/views.py:33,70` e
   `apps/conversations/services/universal_conversation_service.py:165` (PR #298 cobre esses).

3. **P1 — Testes de contrato:** OTP WhatsApp, zonas de entrega, checkout payload, orders by token
   e guardrails do agente (item crítico do CLAUDE.md ainda pendente).

4. **P2 — Namespace mobile/customer:** endpoints limpos para detalhe/status/rastreio/reordenação
   de pedidos (item crítico do CLAUDE.md).
