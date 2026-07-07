# EVOLUCAO_SERVER.md — Backlog e Histórico do Loop Diário

## PRs Abertos (gate anti-acúmulo)

| PR | Branch | Tema | Prioridade |
|----|--------|------|-----------|
| #290 | bot/server-2026-07-01-idor-variant-combo-write | IDOR is_staff em variantes/combos | P1 |
| #291 | bot/server-2026-07-02-store-data-idor-account | IDOR store_data account_id + info-disclosure str(e) | P1 |
| #292 | bot/server-2026-07-03-order-token-throttle | Throttle 30/min OrderByToken/PaymentStatus | P2 |
| #293 | bot/server-2026-07-04-order-number-csprng | order_number com CSPRNG (secrets.randbelow) | P2 |
| #294 | bot/server-2026-07-05-serializer-write-idor | IDOR write serializers: coupon/delivery-zone/order | P1 |
| #295 | bot/server-2026-07-06-serializer-idor-integration-webhook-print | IDOR write: integration/webhook/print-agent serializers | P1 |

## Sessão 2026-07-07

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

## Histórico de Sessões Anteriores

| Data | Fix | Prioridade |
|------|-----|-----------|
| 2026-07-06 | IDOR write: StoreIntegration/Webhook/PrintAgent serializers (PR #295) | P1 |
| 2026-07-05 | IDOR write: StoreSlugOrIdField, DeliveryZone, Order serializers (PR #294) | P1 |
| 2026-07-04 | order_number CSPRNG (secrets.randbelow) (PR #293) | P2 |
| 2026-07-03 | Throttle 30/min em OrderByToken e PaymentStatus (PR #292) | P2 |
| 2026-07-02 | IDOR store_data via account_id + info-disclosure str(e) (PR #291) | P1 |
| 2026-07-01 | IDOR is_staff bypass em variantes/combos (PR #290) | P1 |
