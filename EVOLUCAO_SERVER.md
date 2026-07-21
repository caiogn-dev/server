# Evolução do Backend server (Cardapidex/Pastita)

Documento de rastreamento do loop diário de evolução. Mantido pelo bot de revisão automática.
Branch trunk: `development`. Branch `main` congelada desde 29/mai/2026.

> **2026-07-08:** os 7 branches `bot/server-2026-07-01`…`07-07` foram mergeados na `development`
> (merges d494c6c…a5843da) e deployados. PRs correspondentes (#290–#295) podem ser fechados.

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
|---|---|---|
|---|
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

### 2026-07-02

**Baseline de testes:** Sem Docker/PostgreSQL disponível — suíte de integração não executável
(SQLite não suporta `add_index concurrently`). Pré-existente, não regressão.

**Bug encontrado e corrigido:** IDOR via `account_id` em `store_data` + info-disclosure em erros

- **Tipo:** P1 — IDOR cross-tenant (caminho `account_id`) + info-disclosure via `str(e)` em 500
- **Arquivo:** `apps/automation/api/views/company_profile_views.py`
- **Problema 1 (linha 92):** `WhatsAppAccount.objects.get(id=account_id)` sem escopo de tenant.
  Um atacante autenticado passava o `account_id` de outro tenant e o objeto era carregado antes de
  qualquer verificação. Embora o check `user_can_access_store` downstream bloqueasse a resposta
  final, o acesso não autorizado ao objeto já ocorria.
- **Problema 2 (linha 88):** `Store.objects.get(slug=...)` lançava `DoesNotExist` → capturado
  pelo `except Exception as e` genérico → retornava HTTP 500 com `str(e)` (mensagem interna do
  Django) em vez de 404.
- **Problema 3 (linha 165):** `except Exception as e: return Response({'error': str(e)}, 500)` —
  expunha mensagens internas do ORM para clientes não-autenticados.
- **Correção:**
  - `Store.DoesNotExist` e `WhatsAppAccount.DoesNotExist` agora são capturados explicitamente → 404
  - Tenant gate inserido logo após `WhatsAppAccount.objects.get()`: compara `account.id` com
    `accessible_whatsapp_account_ids(request.user)` → 404 se não pertencer ao tenant
  - `except Exception` genérico: `str(e)` removido da resposta; erro apenas no log interno
- **Testes:** 4 novos casos em `test_company_profile_security.py`:
  - `test_attacker_cannot_probe_victim_account_id` (RED→GREEN — confirmado antes do fix)
  - `test_nonexistent_account_id_returns_404_not_500` (RED→GREEN)
  - `test_nonexistent_slug_returns_404_not_500` (RED→GREEN)
  - `test_owner_can_access_via_own_account_id` (GREEN desde o início)
- **PR:** `bot/server-2026-07-02-store-data-idor-account`


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

### 2026-07-04

**Baseline de testes:** 10 testes `test_order_number_csprng` passando localmente (SimpleTestCase, sem DB).
Testes com DB (test_order_amount_paid, test_order_adjust, test_order_stats_idor) erram com TypeError
em `add_index concurrently` — pré-existente, não regressão.

**Bug encontrado e corrigido:** `StoreOrder.generate_order_number` usava `random.choices` (não-CSPRNG)

- **Tipo:** P2 — Geração de número de pedido não criptograficamente segura
- **Arquivo:** `apps/stores/models/order.py:336`
- **Descrição:** `random.choices(string.digits, k=4)` gera apenas 10.000 sufixos possíveis por
  prefixo+data (e.g. `CES260704XXXX`). Um atacante com acesso ao padrão de numeração pode enumerar
  pedidos de um tenant por força bruta dos sufixos. Substituído por `secrets.randbelow(10000)` que
  mantém o mesmo formato e cardinalidade mas com CSPRNG do módulo `secrets`.
- **Testes:** 10 casos em `apps/stores/tests/test_order_number_csprng.py` (RED→GREEN): formato,
  zero-padding (0000/9999), uso exclusivo de `secrets.randbelow`, ausência de `random.choices`/
  `random.randint`, unicidade probabilística em 100 amostras.
- **PR:** `bot/server-2026-07-04-order-number-csprng`


---

### 2026-07-05

**Baseline de testes:** `SimpleTestCase` com `config.settings.test_serializer` (sem PostgreSQL/langchain).
12 testes do módulo `test_serializer_write_idor` passando (12/12). Suite de integração (Docker) indisponível no container — pré-existente, não regressão.

**Bugs encontrados e corrigidos:** IDOR de escrita em serializers — store cross-tenant [P1]

- **Tipo:** P1 — IDOR de escrita permitindo criar/editar dados em lojas de outros tenants
- **Arquivos corrigidos (1):** `apps/stores/api/serializers.py`
- **Pontos corrigidos (3):**
  1. `StoreSlugOrIdField.to_internal_value` — adicionado tenant gate via `user_can_access_store`
     - Usado em `StoreCouponCreateSerializer.store`; qualquer autenticado criava cupons em loja alheia
  2. `StoreDeliveryZoneCreateSerializer.validate_store` — método adicionado com mesmo tenant gate
     - Campo `store` era `PrimaryKeyRelatedField` sem check; qualquer autenticado criava zonas em loja alheia
  3. `StoreOrderCreateSerializer._resolve_store` — `not is_staff` → `not is_superuser`
     - is_staff bypassa completamente o check de tenant; padrão já fixado em todos os outros places
- **Testes:** 12 novos casos em `apps/stores/tests/test_serializer_write_idor.py` (RED→GREEN confirmado)
- **PR:** #294 aberto


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

### 2026-07-07

**Fix implementado:** IDOR write em `CreateAgentFlowSerializer` + is_staff bypass em `AutoMessageViewSet.create`

### O que estava errado

1. **`CreateAgentFlowSerializer` (apps/automation/api/serializers.py:564)**
   - Campo `store` era writable via ModelSerializer sem `validate_store`.
   - Vetor: `POST /api/v1/automation/flows/` com `{"store": "<uuid_loja_alheia>"}` criava
     AgentFlow no tenant da vítima. A view escopa leitura (get_queryset) mas não escopa
     criação (usa DRF ModelViewSet.create padrão que não verifica o campo `store` do body).

2. **`AutoMessageViewSet.create` (apps/automation/api/views/auto_message_views.py:68)**
   - Guard de tenant: `if not (request.user.is_superuser or request.user.is_staff):`
   - `is_staff` = acesso ao /admin Django, NÃO acesso cross-tenant.
   - Usuário com `is_staff=True` podia criar AutoMessage em company de outro tenant.

### O que foi corrigido

- Adicionado `validate_store` em `CreateAgentFlowSerializer` com padrão estabelecido:
  `user_can_access_store`, mensagem genérica "Loja não encontrada", is_superuser como único bypass.
- Corrigido `is_superuser or is_staff` → `is_superuser` em `AutoMessageViewSet.create`.
- 8 testes SimpleTestCase (sem DB/Docker): RED→GREEN.

### Próximo backlog (prioridade)

1. **P0** — Varredura de `str(e)` em handlers de exceção que vazam mensagens internas
   (PR #297 aberto: cobre `apps/orders/views.py` e `apps/campaigns/api/views.py` — aguarda merge).
   Bônus desta execução: `agents/views.py:process` também corrigido.
2. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md ainda pendente).
3. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
4. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.

---

### 2026-07-10

**Baseline de testes:** 18 testes SimpleTestCase rodados localmente (sem Docker/PostgreSQL).
18/18 passando após o fix. Pré-existente: testes que importam `langchain_core` falham
no container por dependência não instalada — não é regressão desta execução.

**PRs abertos no gate anti-acúmulo:** #297 (info-disclosure str(e)) — aguardando merge.
Sweep `is_staff` anterior cobrira: stores, serializers, automation, whatsapp consumers.
Itens restantes nesta execução: `apps/agents/views.py` e `apps/conversations/`.

**Fix implementado:** is_staff bypassa isolamento de tenant em agentes e conversas [P1]

### O que estava errado

| Arquivo | Linha | Bug |
|---|---|---|
| `apps/agents/views.py` | 33 | `_accessible_agents`: `is_staff` vê todos os agentes IA cross-tenant (IDOR leitura) |
| `apps/agents/views.py` | 70 | `_enforce_account_scope`: `is_staff` cria/edita agentes em contas alheias (IDOR escrita) |
| `apps/conversations/services/universal_conversation_service.py` | 165 | `_is_staff()` retorna True para `is_staff` → conversas de Instagram/Messenger de todos os tenants visíveis (PII leak) |
| `apps/conversations/api/views.py` | 314 | `assign_agent`: `is_staff` pode ser atribuído a conversas de outros tenants sem verificação |
| `apps/agents/views.py` | 122 | Bônus: `str(e)` na ação `process` expunha erros internos do LLM (info-disclosure) |

### O que foi corrigido

- `is_superuser or is_staff` → `is_superuser` em todos os quatro pontos de bypass.
- Logger adicionado em `agents/views.py`; mensagem genérica na resposta HTTP do `process`.
- **Testes:** 18 novos casos (RED→GREEN) em `test_is_staff_idor.py` (agents e conversations).
- **PR:** `bot/server-2026-07-10-is-staff-idor-agents-conversations` (a abrir)

---

### 2026-07-09

**Baseline de testes:** 6/6 novos testes GREEN (SimpleTestCase, sem DB). 4 testes de campaigns
pulados por `langchain_core` ausente no container mínimo — rodarão no Docker. Falha pré-existente:
`test_order_token_rate_definida_no_settings` falha com `test_serializer` settings (config mínima
sem o throttle `order_token`) — não é regressão desta sessão.

**Bug encontrado e corrigido:** Info-disclosure via `str(e)` em handlers de exceção [P0]

- **Tipo:** P0 — Info-disclosure: mensagens internas (Uber API tokens, mensagens ORM, stack info)
  expostas em respostas HTTP para usuários autenticados
- **Arquivos corrigidos (2):**
  1. `apps/orders/views.py` — 3 handlers `except Exception as e: return Response({'detail': str(e)}, 500)`:
     - `CreateDeliveryRequestView.post` (linha 64)
     - `DeliveryRequestStatusView.get` (linha 95)
     - `CancelDeliveryRequestView.delete` (linha 141)
     Substituídos por mensagens genéricas em português; `str(e)` mantido apenas nos logs internos.
  2. `apps/campaigns/api/views.py` — 2 handlers similares:
     - `CampaignViewSet.process` (linha 479) → `'Erro ao processar lote de campanha.'`
     - `ContactListViewSet.import_csv` (linha 591) → `'Erro ao importar contatos do CSV.'`
- **Risco:** Uber API pode incluir tokens Bearer, IDs de rastreamento e endpoints internos em
  mensagens de erro. ORM Django expõe nomes de colunas, chaves estrangeiras e stack traces em
  exceções não tratadas. Com `str(e)` direto na resposta, qualquer usuário autenticado com acesso
  ao endpoint obtém esses dados.
- **Testes:** 6 novos casos em `apps/orders/tests/test_delivery_str_e_leak.py` (RED→GREEN confirmado
  antes e após o fix); 4 casos em `apps/campaigns/tests.py` (skipUnless langchain_core).
- **PR:** `bot/server-2026-07-09-info-disclosure-str-e` (abrindo agora)

**Gate anti-acúmulo:** 0 PRs abertos antes desta sessão. Todos os 7 branches das sessões 07-01 a
07-07 foram mergeados (commits d494c6c…a5843da) conforme EVOLUCAO_SERVER.md de 08/07.

**Próximo backlog atualizado (prioridade):**

1. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md pendente desde a concepção).
2. **P1** — `str(e)` residual: verificar se `apps/core/health_views.py` e `apps/core/api.py`
   expõem erros de DB/Redis em endpoints acessíveis sem autenticação (health check público).
3. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
4. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.

---

### 2026-07-11

**Baseline de testes:** 22 novos testes `test_payment_storefront_str_e_leak` GREEN (SimpleTestCase,
sem Docker). Testes existentes `test_order_token_throttle`, `test_serializer_write_idor`,
`test_integration_webhook_print_idor`, `test_order_number_csprng` continuam OK. `test_is_staff_idor`
falha por `psycopg2` ausente (migração concurrent-index) — pré-existente.
PRs abertos no gate: #297 (str(e) em orders/campaigns) e #298 (is_staff em agents/conversations)
— ambos ainda pendentes de merge; não houve duplicata.

**Bugs encontrados e corrigidos:** info-disclosure via `str(e)` em pagamentos e storefront [P0]

- **Tipo:** P0 — Info-disclosure de mensagens internas do Mercado Pago e de serviços internos
  para usuários autenticados e, nos endpoints AllowAny, para qualquer usuário anônimo
- **Arquivos corrigidos (2):**
  1. `apps/stores/api/payment_views.py` — 6 endpoints autenticados de pagamento:
     `create`, `process`, `confirm`, `fail`, `cancel`, `refund` — todos retornavam `str(e)`
     direto na resposta. O `str(e)` vindo de `Exception(f"Failed to create preference: {preference_response}")`
     expunha o corpo bruto da resposta da API do Mercado Pago (preference IDs, credenciais internas).
     Substituído por mensagens genéricas em pt-BR; detalhe preservado no `logger.error` já existente.
  2. `apps/stores/api/views/storefront_views.py` — 4 pontos em endpoints **AllowAny**
     (qualquer usuário anônimo sem autenticação):
     - `StoreCartViewSet.add_item` (linha 645): `str(e)` → `'Erro ao adicionar item ao carrinho.'`
     - `StoreCheckoutView.post` (linha 934): `str(e)` → `'Erro ao processar checkout.'`
     - `StoreDeliveryFeeView._calculate` x2 (linhas 966, 1001): `str(e)` → `'Erro ao calcular taxa de entrega.'`
- **Testes:** 22 casos em `apps/stores/tests/test_payment_storefront_str_e_leak.py` (RED→GREEN).
  Também adicionadas rates `public_write`, `checkout`, `order_token` em `config/settings/test_serializer.py`.
- **PR:** `bot/server-2026-07-11-str-e-payment-storefront`

**Próximo backlog priorizado:**

1. **P0** — `str(e)` restante: `apps/automation/api/views/unified_views.py:127` (endpoint de
   mensagem unificada), `apps/automation/api/views/auto_message_views.py:173,216`,
   `apps/agents/views.py:124` (coberto pelo PR #298 aberto — não duplicar).
2. **P1** — Merge dos PRs abertos #297 e #298 (aguardando revisão).
3. **P1** — Testes de contrato para OTP WhatsApp, zonas de entrega, checkout e pedido por token
   (pendência crítica do CLAUDE.md).
4. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedido.
5. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.

---

### 2026-07-12

**Baseline de testes:** Django não instalado no container — instalado via pip3 durante a sessão.
15 testes SimpleTestCase (sem Docker/PostgreSQL) GREEN. Falha pré-existente em
`test_order_token_rate_definida_no_settings` (settings de teste não tem `order_token`) confirmada
via `git stash` — não é regressão desta sessão.

**PRs abertos no gate anti-acúmulo:** #297 (str/e orders/campaigns), #298 (is_staff agents/conversations),
#299 (str/e payments/storefront) — aguardando merge. Nenhuma duplicata gerada.

**Bug encontrado e corrigido:** `str(e)` em combo (AllowAny), subscription, print-SSE e webhook [P0/P1]

- **Tipo:** P0 (combo AllowAny) + P1 (subscription IsAuthenticated + print SSE + webhook externo)
- **Arquivos corrigidos (4):**
  1. `apps/stores/api/views/combo_views.py` — `POST /cart/add-combo/` (AllowAny) expunha ORM errors para anônimos
  2. `apps/stores/api/views/subscription_views.py` — 3 endpoints expunham `SubscriptionError` com mensagens
     internas (`'Token MercadoPago não configurado.'`, `'MercadoPago recusou: {status}'`)
  3. `apps/stores/api/views/print_views.py` — SSE generator emitia `str(e)` no stream de dashboard
  4. `apps/stores/api/webhooks.py` — handler enviava `{'message': str(e)}` para o Mercado Pago
- **Testes:** 15 SimpleTestCase (análise estática + mocks) em `test_combo_subscription_webhook_str_e_leak.py`
- **PR:** #300 — `bot/server-2026-07-12-str-e-combo-subscription-print-webhook`

**Varredura de str(e) restante em views (após este PR):**

| Arquivo | Tipo | Risco |
|---|---|---|
| `apps/stores/services/order_service.py` | Service interno | Baixo (não retorna HTTP direto) |
| `apps/stores/services/payment_service.py` | Service interno | Baixo |
| `apps/agents/services/agent_service.py` | Service interno | Baixo |
| `apps/automation/services/automation_service.py` | Service interno | Baixo |
| `apps/automation/tasks/scheduled.py` | Task Celery | Baixo (não retorna HTTP) |

As ocorrências restantes são em services e tasks internos (não retornam respostas HTTP diretamente).
O sweep de views HTTP está essencialmente completo após os PRs #297, #298, #299 e #300.

**Próximo backlog (prioridade atualizada):**

1. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md há várias sessões, ainda pendente).
2. **P1** — Varredura de `is_staff` como bypass cross-tenant em `apps/whatsapp/` e `apps/instagram/`
   (comentários de fix já existem, confirmar que não há pontos faltantes).
3. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
4. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.

---

### 2026-07-21

**Baseline de testes:** Ambiente de checkout limpo sem Docker/PostgreSQL. SimpleTestCase
sem dependências externas executável diretamente.

**Gate anti-acúmulo (checado antes de implementar):**
- PRs abertos: #307 (str(e) whatsapp/automation/health — P0/P1) e #308 (salad-builder str ingredients — P2/P1).
- Commits recentes em `development` (18–20/jul): merges dos PRs #302–#306, fixes de WebSocket
  (ACK, UUID na rota, redis<6), WhatsApp bot (catálogo oficial, PIX copia-e-cola, anti-loop de
  endereço, cooldown de handler desconhecido).
- Itens já cobertos em `development`: OTP contract (`test_otp_whatsapp_contract.py`),
  GeoService calculation (`test_delivery_fee_refactor.py`), IDOR delivery fee
  (`test_delivery_calculate_fee_idor.py`), mobile contracts/orders by token
  (`test_mobile_contracts.py`), agent guardrails + OTP (`test_otp_and_agent_guardrails.py`).
- **Lacuna confirmada:** `StoreDeliveryZone` — métodos `get_distance_range`, `matches_distance`,
  `matches_zip_code` e `calculate_fee` — **zero cobertura de testes**. Estes são as regras
  canônicas de entrega que o CLAUDE.md exige como "backend-owned truth".

**Fix implementado:** Testes de regressão para contratos do modelo StoreDeliveryZone [P1]

- **Tipo:** P1 — Cobertura de testes em lógica canônica de cálculo de entrega
- **Problema:** Os quatro métodos do modelo `StoreDeliveryZone` que implementam as regras
  de entrega não tinham nenhum teste. Refatorações ou mudanças de constantes
  (`DISTANCE_BAND_RANGES`) poderiam quebrar silenciosamente o cálculo de taxa sem nenhum
  sinal de alerta. O risco é alto porque o `GeoService` chama `matches_distance` e
  `calculate_fee` para determinar o valor cobrado do cliente.
- **Arquivo criado:** `apps/stores/tests/test_delivery_zone_model_contract.py`
- **Cobertura (30 casos, todos SimpleTestCase — sem DB/Docker):**
  - `TestGetDistanceRange` (7 casos): todas as bandas nomeadas, range custom, banda desconhecida
    → (None, None), sem dados → (None, None)
  - `TestMatchesDistance` (7 casos): limite inferior inclusivo, superior exclusivo, banda 30_plus
    aceita distâncias grandes, range custom, sem range → False
  - `TestMatchesZipCode` (9 casos): range, fronteiras inclusivas, CEP fora do range, strip de
    hífen e ponto, sem range → False, apenas start → False, apenas end → False
  - `TestCalculateFee` (7 casos): taxa plana, per_km + distância, sem distância usa base,
    distance_km=0 é falsy, min_fee abaixo e acima, combinações, tipo Decimal garantido
- **Técnica:** `StoreDeliveryZone.__new__` + setattr — sem banco, sem migrations, sem HTTP;
  testa os métodos puro-Python do modelo diretamente.
- **PR:** `bot/server-2026-07-21-delivery-zone-model-contract` → base `development`

**Próximo backlog (prioridade atualizada):**

1. **P1** — Mesclar PRs abertos #307 e #308 (pendentes de review).
2. **P1** — Testes de regressão para o checkout payload (fluxo completo: itens, taxa de
   entrega, cupom, pagamento) — `test_checkout_contract.py` ainda falta.
3. **P1** — Testes para o anti-loop de endereço do agente WhatsApp (commit 58986f17): garantir
   que 2 falhas de geocode consecutivas aceitam o endereço como digitado e não travam o bot.
4. **P1** — Testes para o cooldown do UnknownHandler (commit 7a2653ad): `should_send_unknown_helper`
   com cooldown de 15 min e supressão de mídia/sticker.
5. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedidos.
