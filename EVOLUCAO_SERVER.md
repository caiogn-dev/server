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
- **Correção:** Substituído `_accessible_accounts()` (inexistente) por `accessible_whatsapp_account_ids(user)`.
- **PR:** #281 (mergeado)

---

### 2026-06-29

**Baseline de testes:** 13 testes do módulo `test_pii_log_enforcement` rodados localmente. Docker indisponível.

**Bug encontrado e corrigido:** PII (telefones) em logs — violação de LGPD art. 46

- **Tipo:** P0 — Vazamento de dado pessoal sensível em logs de produção
- **Arquivos corrigidos (7):** `core/auth/views.py`, `whatsapp_auth.py`, `session_manager.py`,
  `webhook_service.py`, `order_service.py`, `campaign_service.py`, `whatsapp/webhooks/views.py`
- **Testes:** 13 novos casos em `test_pii_log_enforcement.py` (RED→GREEN)
- **PR:** #282 (mergeado)

---

### 2026-07-01

**Baseline:** IDOR P1 em product_views.py confirmado.

**Bug encontrado e corrigido:** `is_staff` bypassa isolamento de tenant em variantes e combos

- **Tipo:** P1 — IDOR de leitura e escrita (is_staff ≠ is_superuser per convenção do projeto)
- **Arquivos corrigidos:** `apps/stores/api/views/product_views.py` (3 checkpoints)
- **Testes:** 8 novos casos em `test_is_staff_idor.py` (RED→GREEN) + 7 regressões mantidas
- **PR:** #290 (aberto)

---

### 2026-07-02

**Baseline:** IDOR P1 em company_profile_views.py confirmado.

**Bug encontrado e corrigido:** IDOR via `account_id` + info-disclosure em `store_data`

- **Tipo:** P1 — IDOR cross-tenant em endpoint de configuração de automação + `str(e)` exposto
- **Arquivo corrigido:** `apps/automation/api/views/company_profile_views.py` (linhas 92-116)
- **Testes:** 4 novos casos em `test_company_profile_security.py` (RED→GREEN)
- **PR:** #291 (aberto)

---

### 2026-07-03

**Baseline de testes:** 9/9 testes novos GREEN em `SimpleTestCase` (sem DB/Redis/Docker).
34 testes `test_pii_log_enforcement` e afins continuam passando. Erros pré-existentes
de `add_index concurrently` (PostgreSQL) mantidos — não são regressão desta execução.

**PRs abertos no gate anti-acúmulo:** #290 (is_staff IDOR) e #291 (store_data IDOR) —
ambos P1, aguardando merge. Não há duplicata a evitar.

**Fix implementado:** Throttle dedicado para endpoints públicos de pedido por token

- **Tipo:** P2 — Defesa em profundidade em endpoints AllowAny com dados sensíveis
- **Problema:** `OrderByTokenView` (`GET /api/v1/mobile/orders/by-token/{token}/`) e
  `PaymentStatusView` (`GET /api/v1/mobile/orders/{id}/payment-status/`) herdavam apenas o
  `AnonRateThrottle` global (120/min) sem throttle explícito. 120/min = 7.200/hora por IP —
  alto para endpoints que expõem itens, endereço e código PIX sem autenticação.
- **Correção:**
  - `apps/stores/api/webhooks.py`: importa `AnonRateThrottle`, define `_OrderTokenThrottle`
    (`scope='order_token'`), adiciona `throttle_classes = [_OrderTokenThrottle]` nas duas views.
  - `config/settings/base.py`: adiciona `'order_token': '30/minute'` em `DEFAULT_THROTTLE_RATES`.
- **Análise de risco:** `access_token` é `secrets.token_urlsafe(32)` (256-bit entropy).
  Brute-force é computacionalmente inviável. O throttle é defesa em profundidade contra DoS
  no DB e varredura estatística. Reduz para 1.800 req/hora/IP (vs 7.200 antes).
- **Testes:** 9 novos casos em `apps/stores/tests/test_order_token_throttle.py`:
  - 5 testes de configuração (`SimpleTestCase`) — scope, herança, presença nas views, rate
  - 4 testes funcionais com `patch.dict(SimpleRateThrottle.THROTTLE_RATES)` — confirma 429
    na 2ª request com rate=1/min, sem dependência de DB ou Redis
- **PR:** `bot/server-2026-07-03-order-token-throttle` (abrindo agora)

---

## Backlog priorizado

| Prioridade | Arquivo/Endpoint | Problema | Status |
|---|---|---|---|
| P0 | apps/audit/api/views.py:140 | NameError + IDOR em export conversas | **Corrigido PR #281** |
| P0 | apps/core/auth/ + whatsapp + campaigns | PII em logs (telefones, PIX, credenciais) | **Corrigido PR #282** |
| P1 | apps/stores/api/views/product_views.py | IDOR is_staff em variantes e combos | **PR #290 aberto** |
| P1 | apps/automation/api/views/company_profile_views.py | IDOR account_id + str(e) exposto | **PR #291 aberto** |
| P2 | apps/stores/api/webhooks.py | Rate limiting explícito em by-token endpoints | **Corrigido 2026-07-03** |
| P2 | apps/stores/models/order.py:generate_order_number | `random.choices` em order_number (4 dígitos, apenas 10k possibilidades por dia) | **Pendente** |
| P3 | apps/stores/api/webhooks.py | `str(e)` em linha 72 (`str(e)` no status de erro de webhook) — info-disclosure menor | **Pendente** |

---

## Próximo passo priorizado

**P2 — `order_number` gerado com `random.choices` (não CSPRNG):**

`StoreOrder.generate_order_number()` usa `random.choices(string.digits, k=4)` — apenas 10.000
possibilidades por prefixo+data. Combinado com o fato de que o prefixo e a data são previsíveis,
o espaço de enumeração é pequeno. Embora isso não conceda acesso direto (o access_token ainda é
necessário para ler dados), é inconsistente com as práticas de segurança do projeto.

Fix: substituir `random.choices` por `secrets.token_hex(2)` ou `secrets.randbelow(10000)` para
garantir CSPRNG no identificador público do pedido.

**Alternativa (caso os P1 ainda estejam abertos):** aguardar merge dos PRs #290 e #291 e
fazer um sweep de todos os `random.choices` no codebase para garantir que nenhum é usado
em contexto de segurança.
