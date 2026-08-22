# Evolução do Backend server (Cardapidex/Pastita)

Documento de rastreamento do loop diário de evolução. Mantido pelo bot de revisão automática.
Branch trunk: `development`. Branch `main` congelada desde 29/mai/2026.

> **2026-07-08:** os 7 branches `bot/server-2026-07-01`…`07-07` foram mergeados na `development`
> (merges d494c6c…a5843da) e deployados. PRs correspondentes (#290–#295) podem ser fechados.

---

## Histórico de execuções

### 2026-07-23

**Baseline de testes:** 19 testes SimpleTestCase (sem Docker/PostgreSQL/psycopg2) — 19/19 OK.
Falha pré-existente: migrações com `AddIndexConcurrently` requerem psycopg2/PostgreSQL — não é regressão desta sessão.

**Gate anti-acúmulo:** 6 PRs abertos (#307–#312). Nenhum cobre `HandoverLogViewSet`.
Confirmado via leitura do source de `development` HEAD (`fef1b06`).

**Bug encontrado e corrigido:** `HandoverLogViewSet.get_queryset()` — FieldError runtime + isolamento inexistente [P1]

- **Tipo:** P1 — endpoint quebrado em produção (500 para todos os não-superusers) + IDOR (isolamento de tenant nunca executado)
- **Arquivo corrigido (1):** `apps/handover/views.py:332–343`
- **Problema:** `HandoverLog.objects.filter(conversation__store__members=user)`
  — `Conversation` tem campo `account` (FK → `WhatsAppAccount`), **não** `store`.
  — `Store` não tem campo `members` (tem `staff` M2M e `owner` FK).
  — Django levantava `FieldError: Cannot resolve keyword 'store'` para qualquer não-superuser.
  — `GET /api/v1/handover/logs/` sempre retornava 500 para usuários comuns.
  — Não havia isolamento efetivo por tenant (o filtro nunca executava).
- **Correção:** substituído por `conversation__account_id__in=accessible_whatsapp_account_ids(user)`,
  mesmo padrão já usado em `HandoverViewSet.get_conversation()` na mesma view.
- **Testes:** 9 casos em `apps/handover/tests_log_tenant_scope.py` (RED→GREEN confirmado):
  - Source não contém `conversation__store` nem `__members` (caminhos inválidos)
  - Source usa `account_id` e `accessible_whatsapp_account_ids`
  - Superuser → `HandoverLog.objects.all()` sem filtro
  - Não-superuser → `filter(conversation__account_id__in=...)`
  - Não-superuser não chama `objects.all()`
  - Não levanta `FieldError`/`AttributeError`
- **PR:** `bot/server-2026-07-23-handover-log-tenant-scope`

**PRs abertos em produção aguardando merge (não criados por esta sessão):**
| PR | Tipo | Descrição |
|---|---|---|
| #307 | P0/P1 | str(e) em health_views, whatsapp/api/views, automation views |
| #308 | P1 | Ingredientes de salada (string) ignorados na comanda e recibo |
| #309 | P1 | Contratos de cálculo de StoreDeliveryZone (30 testes) |
| #310 | P0 | IDOR no caixa de PDV — gate de tenant em cash_views |
| #311 | P0 | PII cross-tenant em TemplateVariablesViewSet |
| #312 | P1 | IDOR em StoreReviewListView |

**Próximo backlog priorizado:**

1. **P0/P1** — Merge dos PRs #307–#312 (todos aguardando revisão há 1–4 dias).
2. **P1** — Testes de contrato para OTP WhatsApp e checkout (pendência crítica do CLAUDE.md).
   Verificar cobertura real de `test_otp_whatsapp_contract.py` e `test_checkout_*.py`.
3. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedido.
4. **P2** — `base_consumer.py:142` `verify_account_access` usa `is_staff or is_superuser` como fallback;
   se surgir novo consumer sem override, vaza cross-tenant. Adicionar comentário de warning
   ou tornar o método abstrato.


### 2026-07-27

**Baseline de testes:** 10 PRs abertos (#307–#316) aguardando merge; nenhum novo desde #316 (2026-07-26).
HEAD de `development`: `ba8de8c` (fix impressão reimprimir). Novos módulos desde o último histórico:
- `ae62e65` feat(fiscal): módulo NFC-e com provedores Focus NFe + SEFAZ (novo)
- `130c25a` feat(pdv): flag print_receipt gera cupom
- `83c7071` feat(pdv): baixa de estoque na criação de pedido PDV
- `ba8de8c` fix(impressao): Reimprimir cria job novo

**Gate anti-acúmulo:** PRs #307–#316 cobrem export-views-IDOR, toca-delivery HMAC, campaign-account IDOR,
handover-log FieldError, review-list IDOR, marketing PII, cash-register IDOR, delivery-zone tests,
salad-builder string ingredients, str(e) em handlers. Nenhum cobre o módulo `apps/fiscal`.

**Bug encontrado e corrigido:** str(exc) info-disclosure no módulo fiscal NFC-e [P2]

- **Tipo:** P2 — Info-disclosure consistente com o sweep P0/P1 de PRs #297-#307; completa o padrão.
- **Arquivos corrigidos (3):**
  1. `apps/fiscal/providers/sefaz.py` — `SefazProvider.emit_nfce()` levantava `FiscalNotConfigured`
     com mensagem contendo o caminho interno `apps/fiscal/providers/sefaz.py`, retornado ao cliente
     via `Response({'error': str(exc)})`. Caminho removido; instrução ao operador preservada.
  2. `apps/fiscal/services.py` (mensagem FiscalNotConfigured) — mensagem de "Loja sem config fiscal"
     continha `store.metadata["fiscal"]` revelando a estrutura interna de metadados do modelo Store.
     Substituída por mensagem sem referência a chave interna.
  3. `apps/fiscal/services.py` (except Exception) — `emit_nfce_for_order()` capturava qualquer
     excessão (ConnectionError, Timeout) e armazenava `str(exc)` em `doc.error_message`, que é devolvido
     na resposta HTTP. Uma `requests.ConnectionError` expõe URL interna da Focus API
     (`api.focusnfe.com.br`) e parâmetros de query com UUID do pedido.
     Substituído por mensagem genérica; erro real preservado apenas no `logger.exception`.
- **Bônus:** adicionado `logger.warning` na view `emit_nfce` para capturar `FiscalNotConfigured`
  com contexto (pedido/loja) nos logs internos.
- **Testes:** 6 `SimpleTestCase` em `apps/fiscal/tests/test_nfce_str_exc_disclosure.py` (RED→GREEN):
  - `SefazProvider` message sem caminho de arquivo (2 testes)
  - `SefazProvider` message preserva instrução 'certificado A1' ao operador
  - `services.py` sem `store.metadata["fiscal"]` na exception
  - `services.py` sem `str(exc)` em `doc.error_message` (análise estática)
  - Mock `ConnectionError` → `error_message` genérica (teste comportamental)
- **PR:** `bot/server-2026-07-27-nfce-str-exc-disclosure` (abrindo agora)

**Próximo backlog priorizado (após merge dos 11 PRs abertos):**

| Prioridade | Item |
|---|---|
| P1 | Merge urgente dos PRs P0 #310, #311, #315, #316 (IDOR cash/export + PII marketing + webhook HMAC) |
| P1 | Merge dos PRs P1 #312, #313, #314 (handover FieldError + review IDOR + campaign IDOR) |
| P2 | Merge dos PRs P2 #307, #308, #309 (str/e str/eng + salad ingredients + delivery zone tests) |
| P2 | Varredura de N+1 queries em `emit_nfce_for_order` (prefetch_related para order.items__product) |
| P2 | Namespace mobile: rota `/api/v1/mobile/` já existe — verificar contratos de reordenação |

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

1. **P0** — Varredura de `str(e)` em handlers de excessão que vazam mensagens internas
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

**Bug encontrado e corrigido:** Info-disclosure via `str(e)` em handlers de excessão [P0]

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
  excessões não tratadas. Com `str(e)` direto na resposta, qualquer usuário autenticado com acesso
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

### 2026-07-19

**Baseline de testes:** 16 testes novos GREEN (SimpleTestCase, sem Docker). 4 skipped por
`psycopg2` e `langchain_core` ausentes no container mínimo — pré-existente, não regressão.
Gate anti-acúmulo: 0 PRs abertos (todos os anteriores já mergeados em `development`).

**Situação encontrada:** sweep de `is_staff` em whatsapp/instagram já coberto (comentários
e testes existentes confirmam); 7 pontos de `str(e)` em `Exception` genérica ainda expostos
em respostas HTTP — um deles em endpoint **AllowAny** (público sem autenticação).

**Bug encontrado e corrigido:** `str(e)` em 7 handlers de Exception em views HTTP [P0/P1]

- **Tipo:** P0 — endpoint público (`health_views.py`) + P1 — endpoints autenticados WhatsApp/Automação
- **Arquivo crítico:** `apps/core/health_views.py` — `@permission_classes([AllowAny])`, montado em
  `/api/v1/core/metrics/`. Falhas de DB, Redis e Celery retornavam `str(e)` com host, porta e
  credenciais da string de conexão para qualquer cliente anônimo.
- **Arquivos corrigidos (5):**
  1. `apps/core/health_views.py` — DB (`database_unavailable`), cache (`cache_unavailable`), Celery
     (`celery_unavailable`): `str(e)` preservado apenas no `logger.error` interno.
  2. `apps/core/api/health_views.py` — idem.
  3. `apps/whatsapp/api/views.py` — `force_delete` (500), `business_profile` (502 — protegia tokens
     Meta), `sync_templates` (502 — idem): respostas genéricas pt-BR + logger adicionado.
  4. `apps/automation/api/views/unified_views.py` — `UnifiedProcessView`: `f'Erro ao processar
     mensagem: {str(e)}'` → `'Erro ao processar mensagem.'`
  5. `apps/automation/api/views/auto_message_views.py` — `test_send` e `bulk_update`.
- **Testes:** 16 casos em 3 arquivos (RED→GREEN confirmado).
- **PR:** #307 — `bot/server-2026-07-19-str-e-whatsapp-automation-health`

**Status do sweep de `str(e)` em views HTTP:** COMPLETO. Apenas services/tasks internos restam
(não retornam HTTP direto — risco baixo, não prioritário).

**Próximo backlog (prioridade atualizada):**

1. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md há várias sessões — item de maior valor pendente).
2. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
3. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.
4. **P2** — Varredura de `str(e)` em serviços internos (`order_service`, `payment_service`,
   `agent_service`) para mensagens de erro que possam vazar para Celery task logs externos.
### 2026-07-20

**Baseline de testes:** Django e dependências instaladas via pip no container. 24 testes SimpleTestCase
rodados sem Docker/PostgreSQL. 24/24 GREEN após o fix (3 FAIL antes — RED confirmado).

**PRs abertos no gate anti-acúmulo:** #307 (info-disclosure P0) — sem duplicata.

**Bug encontrado e corrigido:** Ingredientes de salada em formato string ignorados na comanda e no recibo [P1]

- **Tipo:** P1 — Fluxo quebrado: comanda de cozinha e recibo não exibiam ingredientes para pedidos
  do Flutter salad-builder quando enviados como `["Alface", "Tomate", ...]` (lista de strings simples).
- **Causa raiz:** `normalize_custom_salad_payload` (checkout_service) armazena ingredientes corretamente
  como strings ou dicts conforme o que o Flutter envia. Porém tanto `_ingredient_lines` em
  `print_service.py` quanto o loop em `receipt_service.py` só tratavam `isinstance(ing, dict)` e
  silenciosamente ignoravam ingredientes do tipo `str`. Resultado: comanda/recibo saíam sem
  ingredientes para pedidos com formato simplificado do Flutter.
- **Arquivos corrigidos (2):**
  1. `apps/stores/services/print_service.py` — `_ingredient_lines`: adicionado branch
     `elif isinstance(ingredient, str) and ingredient.strip()` para renderizar strings diretamente.
  2. `apps/stores/services/receipt_service.py` — loop de ingredientes do salad-builder: mesma
     adição de branch `elif isinstance(ing, str) and ing.strip()`.
- **Testes (24 SimpleTestCase):** `apps/stores/tests/test_salad_builder_contract.py`
  - `NormalizeCustomSaladPayloadTest` (10 casos): contratos de normalização de payload
  - `IngredientLinesPrintServiceTest` (8 casos): renderização da comanda (RED→GREEN confirmado)
  - `ReceiptIngredientRenderingTest` (5 casos): renderização do recibo
- **PR:** `bot/server-2026-07-20-salad-builder-str-ingredients`

**Próximo backlog (prioridade atualizada):**

1. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md há várias sessões, ainda pendente).
2. **P2** — Testes de contrato para `additional_info` do Mercado Pago Orders API (quality score MP):
   `test_mp_orders_additional_info.py` já existe no repo — verificar se passa com settings de teste.
3. **P3** — Confirmar que todos os PRs de str(e) (#297–#300) foram mergeados em development.

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

---

### 2026-07-22

**Baseline de testes:** 11 novos testes `test_cash_register_idor` GREEN (SimpleTestCase, sem DB).
21 testes de `test_order_number_csprng` + `test_delivery_fee_refactor` continuam passando.
Testes DB (PostgreSQL) não executáveis neste container — pré-existente, não regressão.

**PRs abertos no gate anti-acúmulo:** #307 (str(e) whatsapp/automation/health), #308 (salad-builder
str ingredients), #309 (delivery zone model contract). Nenhum cobre o caixa de PDV.

**Bug encontrado e corrigido:** IDOR no caixa de PDV — gate de tenant em 4 views de cash [P0]

- **Tipo:** P0 — IDOR de escrita em registro financeiro cross-tenant
- **Arquivo:** `apps/stores/api/views/cash_views.py`
- **Problema:** `IsStoreOwnerOrStaff.has_permission()` só verifica ownership quando `store_pk`
  está em `view.kwargs` (roteador nested). As views de caixa usam `store_slug` direto nos kwargs,
  portanto `store_pk` nunca existia e o check sempre retornava `True` para qualquer autenticado.
  Vetor: `POST /api/v1/stores/{slug-alheio}/cash/open/` abria o caixa e registrava o atacante
  como `opened_by`. Idem para movement (sangria/reforço) e close.
- **Correção:** Adicionado `_gate(request, store)` que chama `user_can_access_store`
  explicitamente em todas as quatro views (Open, Current, Movement, Close). Superuser passa
  sem check; sem acesso → 404 (info-hiding).
- **Testes:** 11 SimpleTestCase em `test_cash_register_idor.py` (RED→GREEN confirmado)
- **PR:** `bot/server-2026-07-22-cash-register-idor`

**Backlog de segurança mapeado nesta sessão (próximas execuções):**

| Prioridade | Arquivo | Linha(s) | Problema |
|---|---|---|---|
| P0 | `marketing/api/views.py` | 847, 859 | `preview` retorna PII (nome, telefone) para qualquer email do sistema sem escopo de tenant |
| P0/P1 | `marketing/api/views.py` | 913–918 | `sample_customer` retorna user aleatório sem escopo de loja |
| P1 | `stores/api/views/review_views.py` | 76–90 | `StoreReviewListView` sem gate de tenant (mesmo padrão do cash IDOR) |
| P1 | `marketing/api/views.py` | 64–65 | `EmailTemplate.perform_create` sem `validate_store` → IDOR escrita |
| P1 | `marketing/api/views.py` | 661–662 | `EmailAutomation.perform_create` sem `validate_store` → IDOR escrita |
| P1 | `marketing/api/views.py` | 509 | `debug` usa `IsAdminUser` (is_staff) sem `_user_can_use_store` |
| P2 | `stores/api/views/crm_views.py` | 71–81 | `CustomerSearchView` retorna usuários de outros tenants |
| P2 | `stores/api/views/product_views.py` | 348 | `is_staff` bypassa filtro de combos inativos (dentro do tenant correto) |

**Nota sobre CI:** Jobs `check` e `complexity` falham com infraestrutura pré-existente desde
2026-07-18 (`runner_id=0`, duração ~2s, logs HTTP 404). Não causado por esta PR.

**Segunda correção nesta sessão:** PII cross-tenant em TemplateVariablesViewSet [P0]

- **Tipo:** P0 — Vazamento de PII cross-tenant (LGPD art. 46)
- **Arquivo:** `apps/marketing/api/views.py`
- **Problema 1 — `preview`:** `User.objects.filter(email=customer_email).first()` sem escopo
  de loja permitia a qualquer autenticado obter nome+telefone de clientes alheios via e-mail.
  `Subscriber.objects.filter(email=...)` igual: sem store_id.
- **Problema 2 — `sample_customer`:** `User.objects.filter(is_active=True,...).first()`
  retornava o primeiro usuário do banco inteiro — dados reais de qualquer tenant.
- **Correção:** `preview` usa `Subscriber.filter(email=..., store_id=store_id)` (requer os dois);
  `sample_customer` remove o `User.objects` global, usa apenas `Subscriber` escopado.
- **Testes:** 11 SimpleTestCase em `tests_pii_cross_tenant.py` (RED→GREEN).
  Corrigido também `req._force_auth_user` em `test_cash_register_idor.py` (compatível DRF 3.17).
  22 testes totais passando.
- **PR:** #311 `bot/server-2026-07-22-marketing-pii-cross-tenant`

**Próximo backlog priorizado:**

1. **P1** — `stores/api/views/review_views.py` — `StoreReviewListView` sem gate de tenant (mesmo padrão de IDOR do caixa via store_slug)
2. **P1** — `marketing/api/views.py:64–65` — `EmailTemplate.perform_create` sem `validate_store` → IDOR escrita
3. **P1** — `marketing/api/views.py:661–662` — `EmailAutomation.perform_create` sem `validate_store` → IDOR escrita
4. **P1** — `marketing/api/views.py:509` — `debug` usa `IsAdminUser` (is_staff) sem `_user_can_use_store`
5. **P2** — `stores/api/views/crm_views.py:71–81` — `CustomerSearchView` retorna usuários de outros tenants
6. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedidos
### 2026-07-22

**Baseline de testes:** 24 testes SimpleTestCase (sem Docker/PostgreSQL) GREEN antes desta sessão
(11 cash IDOR + 13 marketing PII). CI do GitHub Actions com falha pré-existente em infra
(runner_id=0, runner_name="", duração ~2s) desde 2026-07-18 — documentado nos PRs.

**Gate anti-acúmulo:** PRs #307–#311 abertos, aguardando merge. Nenhuma duplicata gerada.

**Fix 1 (PR #311):** PII cross-tenant em `TemplateVariablesViewSet` [P0]

- **Tipo:** P0 — Vazamento de PII de subscriber (nome/email/telefone) cross-tenant
- **Vetores corrigidos:**
  - `preview`: `User.objects.filter(email=...)` global removido; `Subscriber` só consultado
    com `store_id` E verificação de `_user_can_use_store(request.user, store_id)`.
  - `sample_customer`: `User.objects.filter(is_active=True, ...)` global removido; subscriber
    só retornado quando `store_id` presente E usuário tem acesso à loja.
- **Arquivos:** `apps/marketing/api/views.py`, `apps/marketing/tests_pii_cross_tenant.py` (13 testes)
- **PR:** #311 — `bot/server-2026-07-22-marketing-pii-cross-tenant`

**Fix 2 (este PR):** IDOR em `StoreReviewListView` [P1]

- **Tipo:** P1 — IDOR: qualquer usuário autenticado lia avaliações e dados de pedidos
  de qualquer loja via `GET /api/v1/stores/{slug-da-vítima}/reviews/`
- **Causa raiz:** `IsStoreOwnerOrStaff.has_permission()` só verifica ownership quando
  `store_pk` está nos kwargs do router nested. A rota usa `store_slug` — gate nunca ativava.
- **Correção:** `get_queryset()` levanta `Http404` quando loja inexistente ou usuário sem acesso
  (info-hiding: mesmo comportamento das cash views do PR #310).
- **Arquivos:** `apps/stores/api/views/review_views.py`, `apps/stores/tests/test_review_list_idor.py` (5 testes)
- **PR:** `bot/server-2026-07-22-review-list-idor` (este PR)

**Próximo backlog priorizado:**

1. **P1** — `marketing/api/views.py:64–65` — `EmailTemplate.perform_create` sem `validate_store` → IDOR write
2. **P1** — `marketing/api/views.py:661–662` — `EmailAutomation.perform_create` sem `validate_store` → IDOR write
3. **P1** — `marketing/api/views.py:509` — `debug` action usa `IsAdminUser` (is_staff) em vez de `_user_can_use_store`
4. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
5. **P2** — `stores/api/views/crm_views.py:71–81` — `CustomerSearchView` retorna usuários de outros tenants
6. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos
### 2026-07-24

**Baseline de testes:** 10 testes `test_order_number_csprng` passando (SimpleTestCase, sem Docker).
Deps instaladas no container: django, djangorestframework, django-cors-headers, django-filter, channels,
celery, Pillow, drf-spectacular, cryptography. Falhas pré-existentes de infra CI (`check` e `complexity`)
com `runner_id=0` afetam todos os PRs desde 2026-07-18 — não são regressão desta sessão.

**PRs abertos no gate anti-acúmulo:** #307–#313 (todos baseados em `fef1b06`). Varredura confirmou
que nenhum cobre `apps/campaigns/api/serializers.py`.

**Varredura de segurança executada:** agente de busca inspecionou `apps/instagram/`, `apps/campaigns/`,
`apps/webhooks/` e encontrou 5 vulnerabilidades não cobertas pelos PRs abertos:

| Achado | Prioridade | Arquivo | Vetor |
|---|---|---|---|
| Toca Delivery webhook sem auth | P0 | `apps/webhooks/dispatcher.py` + handler | POST sem assinatura → falso-entrega de pedido |
| `CampaignSerializer.account` gravável no PATCH | P1 | `apps/campaigns/api/serializers.py` | Sequêstro de conta WA da vítima para mass message |
| `InstagramMediaSerializer.account` gravável | P1 | `apps/instagram/api/serializers.py` | Injeção de mídia na fila de publicação da vítima |
| `InstagramConversationSerializer.account` gravável | P1 | `apps/instagram/api/serializers.py` | Injeção de conversa na inbox DM da vítima |
| `ContactListSerializer.account` gravável no PATCH | P1 | `apps/campaigns/api/serializers.py` | Movimentação de PII (telefones) para tenant alheio |

**Bug corrigido (maior impacto):** `account` gravável em PATCH de campanha e lista de contatos [P1 IDOR]

- **Tipo:** P1 — IDOR de escrita cross-tenant em campanhas e listas de contatos
- **Arquivos corrigidos (1):** `apps/campaigns/api/serializers.py`
  - `CampaignSerializer.Meta.read_only_fields` — adicionado `'account'`
  - `ContactListSerializer.Meta.read_only_fields` — adicionado `'account'`
- **Problema:** `create()` já estava protegido por `CampaignCreateSerializer` + `_user_can_use_account`,
  mas `update()`/`partial_update()` herdados do `ModelViewSet` usavam os serializers sem validação de tenant.
  PATCH com `{"account": victim_id}` transferia campanha para a vítima → Celery enviava mensagens com token WA dela.
- **Testes:** 10 SimpleTestCase em `apps/campaigns/tests_account_field_idor.py` (RED→GREEN confirmado).
  Análise estática + DRF field.read_only + writable_fields + não-regressão para campos pré-existentes.
- **PR:** #314 — `bot/server-2026-07-24-campaign-account-idor`

**CI do PR #314:** jobs `check` e `complexity` falharam com `runner_id=0`, duração 3s, output vazio —
falha de infraestrutura pré-existente desde 2026-07-18, não causada por esta PR.

**Próximo backlog priorizado:**

1. **P0** — Toca Delivery webhook sem autenticação (`apps/webhooks/dispatcher.py`):
   `validate_signature` do handler é dead code — dispatcher nunca o chama. Fix: adicionar branch
   `toca-delivery` em `_verify_signature` com `TOCA_DELIVERY_WEBHOOK_SECRET` + `X-Toca-Signature`.
2. **P1** — `InstagramMediaSerializer.account` e `InstagramConversationSerializer.account` graváveis
   (`apps/instagram/api/serializers.py`): mesmo padrão do fix desta sessão — adicionar `'account'`
   a `read_only_fields` em ambos. Cuidado: `InstagramMediaViewSet.perform_create` também precisa
   validar ownership da conta no create (sem `CampaignCreateSerializer` equivalente).
3. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (pendência crítica do CLAUDE.md há várias sessões).
4. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedidos
   (item crítico do CLAUDE.md).
### 2026-07-24

**Baseline de testes:** Django e dependências instalados via pip no container (sem Docker/PostgreSQL).
Migrações com `AddIndexConcurrently` exigem psycopg2 → testes de integração com DB não executáveis.
8 testes SimpleTestCase (sem DB/Docker) GREEN para a correção desta sessão.
CI do GitHub Actions com `runner_id=0` (infra pré-existente desde 2026-07-18) — não é regressão.

**PRs abertos no gate anti-acúmulo:** #307–#313 verificados — nenhum cobria `apps/webhooks/dispatcher.py`.
Nenhuma duplicata gerada.

**Vulnerabilidade encontrada e corrigida:** toca-delivery aceita POST sem assinatura HMAC [P0]

- **Tipo:** P0 — Forja de status de entrega por atacante anônimo sem credenciais
- **Descrição:** `WebhookDispatcherView._verify_signature` retornava `None` para `toca-delivery`
  sem validar nenhuma assinatura. Qualquer POST anônimo a `/webhooks/v1/toca-delivery/` com
  `corrida_id` de um pedido real atualizava `StoreOrder.status` e `delivered_at` para "entregue".
  `TocaDeliveryHandler.validate_signature()` existia mas **nunca era chamado** (código morto).
- **Arquivos corrigidos:**
  1. `apps/webhooks/dispatcher.py` — adiciona `'toca-delivery'` a `_PROVIDERS_REQUIRE_SIGNATURE`
     (fail-closed: sem secret → 403); implementa branch `elif provider == 'toca-delivery':` com
     HMAC-SHA256 de `request.body` via `TOCA_DELIVERY_WEBHOOK_SECRET` (settings fallback) ou
     `endpoint.secret` (WebhookEndpoint no admin), comparado ao header `X-Toca-Signature`
  2. `config/urls_minimal.py` — adiciona rota `webhooks/v1/` para testes futuros
- **Testes:** 8 SimpleTestCase em `apps/webhooks/tests_toca_delivery_signature.py`:
  fail-closed (sem secret → None), assinatura correta via settings → True, errada → False,
  header ausente → False; mesmos 3 casos via WebhookEndpoint no banco
- **PR:** #315 — `bot/server-2026-07-24-toca-webhook-signature`
- **CI:** `check` e `complexity` falham com `runner_id=0`, 2s de duração — infra pré-existente

**Nota:** PR #314 (campaign/contactlist IDOR) também aberto nesta sessão em branch separado.
Ambos os PRs aguardam merge para `development`.

**Backlog atualizado:**

1. **P0** — `apps/instagram/api/serializers.py` — `InstagramMediaSerializer` e
   `InstagramConversationSerializer`: `account` gravável via PATCH (mesmo padrão do campaign IDOR).
   Adicionar `'account'` a `read_only_fields` + validar `perform_create`.
2. **P1** — Testes de contrato (regressão) para OTP WhatsApp, zonas de entrega e checkout
   (item crítico do CLAUDE.md há várias sessões, ainda pendente).
3. **P1** — Varredura de `is_staff` como bypass cross-tenant em `apps/whatsapp/` e `apps/instagram/`
4. **P2** — Namespace limpo mobile/customer para detalhe/status/rastreio/reordenação de pedidos.
5. **P2** — Suporte a itens customizados de salada (Flutter builder) no checkout/pedido/recibo.
### 2026-07-26

**Baseline de testes:** 46 testes `SimpleTestCase` rodados localmente (sem Docker/PostgreSQL).
46/46 passando após o fix. PRs abertos no gate: #307–#315 (9 PRs abertos, nenhum mergeado desde
19/07). CI `check`/`complexity` falhando por infra desde 2026-07-18 — pré-existente, não regressão.

**Varreduras antes de escolher o fix:**
- `is_staff` em `apps/whatsapp/` e `apps/instagram/`: **limpos** — nenhum bypass encontrado.
- `str(e)` residual em `campaigns/api/views.py:354,374,395,413,431,515`: são `ValueError` de validação
  com mensagens intencionais (ex: "Only running campaigns can be paused") — risco aceitável, P3.
- Fiscal (NFC-e): sem views HTTP expostas — serviço interno apenas.
- SSRF: `StoreWebhookSerializer.validate_url` + `apps.core.url_security` já existem — protegido.
- OTP WhatsApp: `test_otp_whatsapp_contract.py` já existe — coberto.

**Bug encontrado e corrigido:** IDOR cross-tenant em views de exportação [P0]

- **Tipo:** P0 — IDOR de leitura com exfiltração de PII + dados financeiros cross-tenant
- **Arquivo:** `apps/stores/api/export_views.py` — `BaseExportView.get_store()`
- **Problema:** `get_store()` buscava qualquer loja do banco por `?store=<slug/uuid>` sem verificar
  acesso do usuário. `IsStoreOwnerOrStaff` em `permission_classes` não protegia porque só verifica
  ownership quando `store_pk` está em `view.kwargs` — aqui o store vem de query params.
- **Vetor:** `GET /api/v1/stores/export/orders/?store=loja-vitima` → CSV com nome/email/telefone
  de todos os clientes. Mesmo padrão válido para receita, produtos, stock, dashboard, KPIs.
- **Views afetadas (8):** `OrdersExportView`, `RevenueReportView`, `ProductsReportView`,
  `StockReportView`, `CustomersReportView`, `CustomerInsightsReportView`,
  `StoreDashboardStatsView`, `SaladasReportView`.
- **Correção:** Importa `user_can_access_store` + `Http404`. Em `get_store()`: após resolver a loja,
  superuser passa sem gate; demais → `user_can_access_store(user, store)`; se False → `Http404`
  (info-hiding). Bônus: UUID inexistente captura `DoesNotExist` → `None` (antes propagava 500).
- **Testes:** 9 `SimpleTestCase` em `test_export_views_idor.py` (RED→GREEN confirmado).
- **PR:** #316 — `bot/server-2026-07-26-export-views-idor`
- **CI:** jobs `check`/`complexity` falham por infra pré-existente (output vazio, logs 404) — não
  relacionado ao PR. Comentado no #316.

**Próximo backlog (prioridade atualizada):**

1. **P1** — Merge dos PRs acumulados #307–#316 (9 PRs aguardando revisão há até 7 dias).
2. **P1** — Testes de contrato para checkout payload e pedido por token (OTP já coberto).
3. **P2** — Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedido.
4. **P2** — Varredura de IDOR em `apps/stores/api/export_views.py` outras classes (concluída nesta
   sessão), `apps/audit/` (verificar cobertura do fix de 2026-06-28).

### 2026-08-18

**Baseline de testes:** 8 novos testes SimpleTestCase GREEN (sem Docker/PostgreSQL).
Deps instaladas via pip no container: django, drf, celery, channels. Falha pré-existente de
`AddIndexConcurrently` (PostgreSQL) e ausência de psycopg2 — não são regressão desta sessão.

**Gate anti-acúmulo:** 20 PRs abertos (#318–#337) aguardando merge. Varredura confirmou que nenhum
cobre `apps/users/views.py:UnifiedUserActivityViewSet`. HEAD de development: `2eead0f`.

**Varredura executada antes do fix:**
- `str(e)` em respostas HTTP: residual apenas em `storefront_views.py:745` (ValueError de regra de
  negócio intencional — mensagem própria do domínio, P3).
- `is_staff` como bypass cross-tenant: limpo em todos os módulos verificados.
- OTP timing attack: `hmac.compare_digest` já em uso — protegido.
- Candidato escolhido: IDOR de leitura em `UnifiedUserActivityViewSet` (P1).

**Bug encontrado e corrigido:** IDOR de leitura em `UnifiedUserActivityViewSet` — PII de clientes de todos os tenants exposto [P1]

- **Tipo:** P1 — IDOR de leitura cross-tenant (PII: mensagens WA, pedidos, logins de clientes alheios)
- **Arquivo corrigido (1):** `apps/users/views.py` — `UnifiedUserActivityViewSet.get_queryset()`
- **Problema:** `get_queryset()` herdava `super().get_queryset()` que retorna
  `UnifiedUserActivity.objects.all()` sem nenhum filtro de tenant.
  - `GET /api/v1/users/activities/` → listava TODAS as atividades do banco (PII global)
  - `GET /api/v1/users/activities/?user_id=<uuid-alheio>` → atividades de qualquer cliente
  - `activity_type` inclui `whatsapp_message`, `site_order`, `cart_updated`, `site_login`
    e o campo `metadata` (JSONField) pode conter pedidos, endereços, telefones, dados de sessão.
  - O `UnifiedUserViewSet` no mesmo arquivo já tinha `_accessible_unified_users()` corretamente —
    a inconsistência estava apenas no `UnifiedUserActivityViewSet` secundário.
- **Correção:** `get_queryset()` agora chama `_accessible_unified_users(request.user)` para obter
  os IDs dos usuários acessíveis ao tenant, e filtra `UnifiedUserActivity.objects.filter(user_id__in=...)`
  antes de qualquer query param. Filtros por `user_id` e `activity_type` aplicados em cima do
  queryset já escopado — `?user_id` de tenant alheio retorna queryset vazio (info-hiding).
- **Testes:** 8 casos em `apps/users/test_activity_idor.py` (RED→GREEN confirmado):
  - `TestUnifiedUserActivityViewSetIsolamento` (3): análise estática — presença de `_accessible_unified_users`
    em `get_queryset()`, ausência de `objects.all()` no método, presença de `accessible_user_ids`
  - `TestUnifiedUserActivityViewSetComportamento` (3): mocks comportamentais — superuser chama
    `_accessible_unified_users`, usuário comum idem, `?user_id` de alheio ainda chama escopo de tenant primeiro
  - `TestUnifiedUserActivityViewSetAnaliseeEstatica` (2): análise de código — filtros `user_id`
    e `activity_type` preservados após o fix
- **PR:** `bot/server-2026-08-18-activity-idor-tenant-scope` → base `development`

**Próximo backlog priorizado:**

| Prioridade | Item |
|---|---|
| P0 | Merge urgente dos PRs abertos #318–#337 (20 PRs acumulados) |
| P1 | Varredura de IDOR em viewsets de `apps/fiscal/` (NFC-e) — ainda não inspecionados |
| P1 | Testes de regressão para anti-loop de endereço do agente WA e cooldown UnknownHandler |
| P2 | Namespace mobile/customer limpo para detalhe/status/rastreio/reordenação de pedidos |
| P2 | N+1 em `UnifiedUserViewSet.get_queryset()` — `phones_in_conversations` pode ser subquery lazy |
