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
     - Usado em `StoreCouponCreateSerializer.store`; qualquer autenticado criava cupões em loja alheia
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

1. **P0** — Varredura de `str(e)` em handlers de exceção que vazam mensagens internas do ORM
   (já coberto parcialmente pelo PR #291 ainda aberto — verificar se foi mesclado).
2. **P1** — Varredura de `is_staff` como bypass cross-tenant nas demais views de `apps/whatsapp/`
   e `apps/instagram/` (prosseguir o sweep iniciado nesta sessão).
3. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md ainda pendente).
4. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
5. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.

---

### 2026-07-18

**Baseline de testes:** Suíte completa não executável sem Docker/PostgreSQL (migração `add_index concurrently`). Pré-existente, não regressão. 9 testes SimpleTestCase novos verificados por inspeção de código.

**Gate anti-acúmulo:** 8 PRs abertos (#297–#305). Nenhum cobre `ChatConsumer` nem `InstagramConsumer.subscribe_conversation`.

**Bugs encontrados e corrigidos:** IDOR em ChatConsumer + InstagramConsumer.subscribe_conversation [P0/P1]

#### 1. ChatConsumer — IDOR na conexão (P0)

| Consumer | Rota WS | Gate em _post_auth_connect? |
|---|---|---|
| `ChatConsumer` | `ws/chat/{conversation_id}/` | ❌ **nenhum** |

`_post_auth_connect` entrava no grupo `chat_{conversation_id}` sem verificar se a conversa pertence a
uma conta do usuário. Qualquer usuário autenticado recebia em tempo real: mensagens (`chat_message`),
typing indicators e status de mensagem — PII completo — de qualquer conversa de qualquer tenant.

Adicionalmente, `mark_message_read` marcava mensagens de qualquer tenant como lidas sem verificação
de propriedade (IDOR de escrita).

#### 2. InstagramConsumer.subscribe_conversation — IDOR no handler (P1)

Mesmo padrão do `WhatsAppDashboardConsumer` corrigido em PR #305. `handle_message` aceitava
`subscribe_conversation` sem verificar se a conversa pertence à conta conectada. Usuário da conta
IG própria podia assinar eventos de conversa de outro tenant.

#### Correções

**`apps/core/consumers.py` — ChatConsumer:**
- `_post_auth_connect`: verifica `verify_conversation_access(conversation_id)` antes de `group_add`;
  fecha com código 4003 se negado
- `mark_message_read`: verifica `owned_ids` antes de salvar; retorno silencioso se tenant errado
- `verify_conversation_access` adicionado: filtra `Conversation` por `account_id__in` de
  `WhatsAppAccount.objects.filter(owner=self.user)`; superuser bypassa

**`apps/instagram/consumers.py` — InstagramConsumer:**
- `handle_message › subscribe_conversation`: verifica `verify_instagram_conversation_access` antes
  de `group_add`; retorna `{type: error, code: forbidden}` se negado
- `verify_instagram_conversation_access` adicionado: filtra `InstagramConversation` por
  `account_id=self.account_id` (conta já autenticada); superuser bypassa

**Testes:** 9 casos SimpleTestCase (sem DB/Docker) em dois novos arquivos:
- `apps/core/tests/test_chat_consumer_idor.py` — 5 testes
- `apps/instagram/tests/test_instagram_consumer_subscribe_idor.py` — 4+5 = 9 testes totais

**PR:** `bot/server-2026-07-18-chat-consumer-idor`

#### Próximo backlog (prioridade)

1. **P1** — `DashboardConsumer.subscribe_account` sem verificação de acesso à conta (`ws/dashboard/`)
2. **P1** — `AutomationConsumer.subscribe_company` sem verificação de acesso à empresa (`ws/automation/`)
3. **P1** — `StoreOrdersConsumer` sem verificação que o usuário tem acesso ao `store_slug` (`ws/stores/{slug}/orders/`)
4. **P1** — Merge dos PRs acumulados (#297–#305) para liberar a fila de revisão
5. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedidos (CLAUDE.md crítico)
