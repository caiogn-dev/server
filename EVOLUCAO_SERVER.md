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

**Baseline de testes:** 15 testes rodados localmente (sem Docker/PostgreSQL).
`--no-migrations` necessário (migração `add_index concurrently` não roda em SQLite).
Pré-existente, não regressão.

**Bugs encontrados e corrigidos:** IDOR via `is_staff` em variantes e combos (P1)

- **Tipo:** P1 — IDOR de leitura + escrita cross-tenant via flag `is_staff`
- **Contexto:** Convenção do projeto: `is_staff` (acesso ao Django `/admin`) NÃO concede
  acesso cross-tenant; apenas `is_superuser` pode ver/editar dados de qualquer tenant.
- **Arquivos corrigidos (1):** `apps/stores/api/views/product_views.py`
  - `StoreProductVariantViewSet.get_queryset:257` — `is_staff or is_superuser` → `is_superuser`
    (leitura de variantes de qualquer produto sem ser dono)
  - `StoreComboViewSet._assert_store_access:290` — mesmo bypass em create/update/delete de combos
  - `StoreProductTypeViewSet._assert_store_access:374` — mesmo bypass em product-types
- **Testes:** 8 novos casos em `apps/stores/tests/test_is_staff_idor.py` (RED→GREEN confirmado).
  Regressão: `test_combo_product_type_idor` 7/7 mantidos. Total: 15/15.
- **PR:** `bot/server-2026-07-01-idor-variant-combo-write` (a abrir)

---

## Backlog priorizado

| Prioridade | Arquivo | Linha | Problema | Status |
|---|---|---|---|---|
| P0 | apps/audit/api/views.py | 140 | NameError + IDOR em export conversas | **Corrigido (PR #281 merged)** |
| P0 | apps/core/auth/views.py | 76 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/core/auth/whatsapp_auth.py | 235, 281 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/automation/services/session_manager.py | 260, 467, 477, 487 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/webhook_service.py | 1108, 1442, 1488, 1498 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/order_service.py | 33, 401, 405, 491, 548 | PII em log — telefone + PIX parcial | **Corrigido 2026-06-29** |
| P0 | apps/campaigns/services/campaign_service.py | 321, 380, 383 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/webhooks/views.py | 71 | Credencial (verify_token) em log | **Corrigido 2026-06-29** |
| P1 | apps/automation/api/views/company_profile_views.py | 92-98 | IDOR — account_id não validado | **Corrigido (user_can_access_store já presente)** |
| P1 | apps/stores/api/views/product_views.py | 257, 290, 374 | IDOR — is_staff bypassa tenant em variantes/combos | **Corrigido 2026-07-01** |
| P2 | apps/mobile_api/urls.py | — | Sem rate limiting em /orders/by-token/ | **Pendente** (token 128-bit mitiga risco) |

---

## Próximo passo priorizado

**P2 — Rate limiting em /orders/by-token/**: Endpoint `OrderByTokenView` (AllowAny, sem auth)
expõe dados de pedido (endereço, código PIX) para quem tem o token. O token é `secrets.token_urlsafe(32)`
(128 bits de entropia), então brute force é inviável. Risco residual: scanning de tokens vazados.
Mesmo assim, throttling é boa prática defensiva.

Fix: adicionar `throttle_classes = [AnonRateThrottle]` com scope `order_by_token`
(ex: 60/min por IP) em `OrderByTokenView`, reutilizando o padrão de `_GeoThrottle` em
`maps_views.py`. Adicionar `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['order_by_token']` em settings.
