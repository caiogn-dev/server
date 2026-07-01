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

## Backlog priorizado

| Prioridade | Arquivo | Linha | Problema | Status |
|---|---|---|---|---|
| P0 | apps/audit/api/views.py | 140 | NameError + IDOR em export conversas | PR #281 aberto |
| P0 | apps/core/auth/views.py | 76 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/core/auth/whatsapp_auth.py | 235, 281 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/automation/services/session_manager.py | 260, 467, 477, 487 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/webhook_service.py | 1108, 1442, 1488, 1498 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/services/order_service.py | 33, 401, 405, 491, 548 | PII em log — telefone + PIX parcial | **Corrigido 2026-06-29** |
| P0 | apps/campaigns/services/campaign_service.py | 321, 380, 383 | PII em log — telefone | **Corrigido 2026-06-29** |
| P0 | apps/whatsapp/webhooks/views.py | 71 | Credencial (verify_token) em log | **Corrigido 2026-06-29** |
| P1 | apps/automation/api/views/company_profile_views.py | 92-98 | IDOR — account_id não validado antes de uso | **Pendente** |
| P2 | apps/mobile_api/urls.py | — | Sem rate limiting em /orders/by-token/ | **Pendente** |

---

## Próximo passo priorizado

**P1 — IDOR em company_profile_views.py:92-98**: `account_id` recebido na request não é validado
contra o tenant do usuário autenticado antes de ser usado para buscar configuração. Um usuário de
Tenant A pode consultar/alterar dados do Tenant B se conhecer o `account_id`.

Fix: adicionar verificação `get_object_or_404(WhatsAppAccount, id=account_id, store=user_store)`
antes de qualquer operação, semelhante ao padrão já usado em outros ViewSets.
