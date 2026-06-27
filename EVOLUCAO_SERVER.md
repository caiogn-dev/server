# EVOLUCAO_SERVER.md

Backlog priorizado + histórico de execuções do loop diário de evolução do backend `server`.

---

## Estado do Baseline de Testes (2026-06-27)

- **Suíte principal**: 388 passando, 8 falhando (pré-existentes, não bloqueadores)
- **Falhas pré-existentes** (sem Redis/RabbitMQ no CI):
  - `test_checkout_menu_invalidation` (2) — requer Celery/AMQP
  - `test_menu_context_cache` (5) — requer Redis
  - `test_dynamic_context::test_output_identical_snapshot` (1) — snapshot divergente
- **Migrations PostgreSQL-específicas** (`AddIndexConcurrently`): ignoradas com `--no-migrations` no CI sem Postgres

---

## Histórico de Execuções

### 2026-06-27 — IDOR Instagram: is_staff como bypass de tenant (P0)

**O que foi medido**: Todos os 4 ViewSets do app `instagram` e 2 métodos do `InstagramShoppingViewSet` usavam `is_superuser or is_staff` como bypass de isolamento de tenant, permitindo que qualquer usuário com `is_staff=True` (admin de uma loja) acessasse dados de contas Instagram de **qualquer outro usuário**.

**Arquivos modificados**: `apps/instagram/api/views.py`

**Fix**: Substituição de `is_staff` por `is_superuser` em todos os contextos de acesso cross-tenant (6 ocorrências), conforme convenção do projeto (CLAUDE.md: "use `is_superuser` (not `is_staff`) para owner cross-tenant"). Adicionalmente, no `InstagramConversationViewSet`, o filtro `account__user` foi movido para **antes** do filtro `account_id` da query string, prevenindo IDOR via parâmetro de URL.

**ViewSets corrigidos**:
- `InstagramAccountViewSet.get_queryset()`
- `InstagramMediaViewSet.get_queryset()`
- `InstagramLiveViewSet.get_queryset()`
- `InstagramConversationViewSet.get_queryset()`
- `InstagramShoppingViewSet.get_account()`
- `InstagramShoppingViewSet.tag_product()`

**Testes**: 9 novos em `apps/instagram/tests/test_idor_is_staff.py` — todos passando.

**PR**: `bot/server-2026-06-27-instagram-idor-is-staff`

---

## Backlog Priorizado

### P0 — Segurança crítica

- [x] IDOR em SSE sem token na query string (e615fe1)
- [x] Open redirect no login do painel (11de630)
- [x] IDOR em subscribe_conversation WebSocket (7a8e028)
- [x] IDOR em send_* do WhatsApp (1d7e1ad)
- [x] IDOR em Marketing (239d881)
- [x] IDOR em Campaigns (f3d6e21)
- [x] IDOR em relatórios (9c7b2fa)
- [x] IDOR em CompanyProfile store_data/create (1a64db6)
- [x] IDOR em handover por tenant (b7facfc)
- [x] SSRF em webhook URL de loja (fb7d075)
- [x] Criptografia de page_access_token/app_secret do Messenger (e3c0519)
- [x] Auth e tenant check em delivery Uber (44ebbf8)
- [x] IDOR em Instagram — is_staff como bypass de tenant (2026-06-27)
- [ ] **IDOR em `StoreDeliveryZoneViewSet.calculate_fee()`** — consulta `StoreDeliveryZone.objects.filter(store_id=...)` diretamente sem verificar acesso do usuário à loja (`delivery_views.py:93`)
- [ ] PII em resposta mobile: `customer_email` com placeholder `{phone}@pastita.local` exposto em `CustomerOrderDetailView` (`webhooks.py:706`)

### P1 — Bugs de produção / fluxos quebrados

- [x] IDOR + AttributeError em `StoreCouponViewSet.validate()` (PR #279 aberto)
- [ ] Namespace dedicado para detalhe/status/tracking/reorder de pedidos mobile (CLAUDE.md item 1)
- [ ] Itens de salada customizados do Flutter no checkout/pedido/recibo (CLAUDE.md item 2)

### P2 — Performance / Qualidade

- [x] N+1 em inbox de conversas (47330bd)
- [x] N+1 em catálogo de produtos (069ea7f)
- [x] N+1 em clientes/endereços (cde47f8)
- [x] Dashboard charts via GROUP BY (55c26e1)
- [ ] Testes de regressão para: OTP WhatsApp, zonas de entrega, cálculo de rota, payload de checkout, pedidos by-token, guardrails do agente (CLAUDE.md item 3)

### P3 — Limpeza / Dívida técnica

- [ ] Remover dependência HERE Maps (se existir); Google Maps é o canônico (CLAUDE.md item 4)
- [ ] Centralizar taxa de entrega no backend; remover qualquer hardcode no Flutter (CLAUDE.md item 5)

---

## Próximo item prioritário

**`StoreDeliveryZoneViewSet.calculate_fee()`** — consulta direta sem tenant check (P0, `delivery_views.py:93`). Um usuário staff de qualquer loja pode calcular taxas de entrega de lojas concorrentes. Fix: usar `self.get_queryset()` ou adicionar verificação `user_can_access_store()`.
