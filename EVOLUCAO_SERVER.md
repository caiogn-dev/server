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

### 2026-07-06

**Baseline de testes:** 15 novos testes `test_integration_webhook_print_idor` rodados sem Docker
(SimpleTestCase + mocks). 15/15 passando após o fix. Pré-existente: suíte completa requer
PostgreSQL/Docker; migrações com `add_index concurrently` continuam falhando por design.

**Bug encontrado e corrigido:** IDOR de escrita em serializers — Onda 2 (P1)

- **Tipo:** P1 — IDOR de escrita cross-tenant em três serializers
- **Descrição:** Continuação do sweep do PR #294 (Onda 1). Três serializers em
  `apps/stores/api/serializers.py` expunham o campo `store` como writable sem `validate_store`,
  permitindo que um usuário com acesso à loja A passasse `store=<UUID da loja B>` no body e
  criasse recursos no tenant alheio, mesmo a permissão `IsStoreOwnerOrStaff` validando apenas
  o `store_slug` da URL.
- **Arquivos corrigidos (1):** `apps/stores/api/serializers.py`
  - `StoreIntegrationCreateSerializer` — integração WA/meta criada em tenant alheio
  - `StoreWebhookSerializer` — webhook criado em tenant alheio (risco de exfiltração de pedidos)
  - `StorePrintAgentCreateSerializer` — print agent criado em tenant alheio
- **Padrão do fix** (idêntico ao PR #294): `validate_store` com `user_can_access_store`
  + `is_superuser` como único bypass cross-tenant + info-hiding ('Loja não encontrada')
- **Testes:** 15 novos casos em `apps/stores/tests/test_integration_webhook_print_idor.py`
  (RED→GREEN confirmado)
- **PR:** `bot/server-2026-07-06-serializer-idor-integration-webhook-print`

---

## Backlog priorizado

| Prioridade | Arquivo/Área | Linha | Problema | Status |
|---|---|---|---|---|
| P0 | apps/audit/api/views.py | 140 | NameError + IDOR em export conversas | PR #281 aberto |
| P0 | apps/core/auth/views.py | 76 | PII em log — telefone | **Corrigido 2026-06-29** (PR merged) |
| P0 | apps/core/auth/whatsapp_auth.py | 235, 281 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/automation/services/session_manager.py | 260+ | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/webhook_service.py | 1108+ | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/order_service.py | 401+ | PII em log — PIX | **Corrigido 2026-06-29** |
| P0 | apps/campaigns/services/campaign_service.py | 321+ | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/webhooks/views.py | 71 | Credencial em log | **Corrigido 2026-06-29** |
| P1 | apps/automation/api/views/company_profile_views.py | 92-98 | IDOR store_data via account_id | **Corrigido 2026-07-02** (PR #291) |
| P1 | apps/stores/api/views/product_views.py | 257,290,374 | IDOR is_staff em variantes/combos | **Corrigido 2026-07-01** (PR #290) |
| P1 | apps/stores/api/serializers.py | StoreSlugOrIdField+Delivery+Order | IDOR write Onda 1 | **Corrigido 2026-07-05** (PR #294) |
| P1 | apps/stores/api/serializers.py | Integration+Webhook+PrintAgent | IDOR write Onda 2 | **Corrigido 2026-07-06** (este PR) |
| P2 | apps/mobile_api/ | — | Throttle em /orders/by-token/ | **Corrigido 2026-07-03** (PR #292) |
| P2 | apps/stores/models/order.py | 336 | order_number não CSPRNG | **Corrigido 2026-07-04** (PR #293) |

---

## Próximo passo priorizado

**Sweep de outros serializers com campo writable sem `validate_store`** — a varredura das duas ondas
cobriu `apps/stores/api/serializers.py`. Verificar se outros apps têm o mesmo padrão:
- `apps/automation/api/serializers.py` — campos de store/account sem validate
- `apps/whatsapp/api/serializers.py` — idem
- Testes de contrato para OTP, zonas de entrega, checkout e agent guardrails (item crítico do CLAUDE.md)
