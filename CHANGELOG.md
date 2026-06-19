# Changelog

Mudanças relevantes do server2. Deploy é a imagem baked (`Dockerfile.prod`) — commits aqui são histórico/higiene; só valem em prod após recreate/rebuild. Ver `DEPLOYMENT_RULES.md`.

## 2026-06-19 — lote `development` (11 commits temáticos)

Working tree que estava acumulado foi organizado em commits por frente.

### Segurança
- **is_staff não concede acesso cross-tenant** (`0d62a19`): só `is_superuser` vira role `owner`. Antes, qualquer conta com acesso ao `/admin` enxergava/editava dados de todas as lojas. Inclui verificação de assinatura do webhook MercadoPago em `postado/api/views`.

### Performance
- **N+1, índices, cache e locks** (`13743a0`): health_check do dashboard cacheado 30s (tira ~2.9s de `inspect.active()` do request); índices `order(store,status,created_at)` e `customer(whatsapp)`; prefetch de combo_items / select_related product_type+variants / subquery annotations; `event_bus.unsubscribe` corrigido; `select_for_update(nowait)` tratando `OperationalError`.

### Funcionalidades
- **Refactor LLM — Task 1** (`bc6b28e`): `apps/agents/runtime/factory.py` (create_llm/create_redis_client + get_llm cacheado por agente) extraído da LangchainService; migration 0009 (índice agent+phone); spec/plano da centralização.
- **Observabilidade** (`3ab472d`): log rotation (50m×5) em todos os serviços, GlitchTip via `SENTRY_DSN` opcional, serviço Flower (dashboard Celery); `flower>=2.0.1`.
- **WhatsApp / bot** (`abf9d30`): `tests.py` → pacote `tests/`, migration 0007 (índice account+created em Message), handlers catalog/interactive + webhook_service, docs MESSAGING_BOT_ARCHITECTURE e COEX_META_APROVACAO (Embedded Signup Coexistence).
- **Delivery fee + geo** (`e632212`): SSOT da taxa em `DeliveryQuoteService.calculate_dynamic_fee` (base + R$1/km após 4km); geo/maps via reverse no backend cacheado.
- **Billing** (`32707c3`): subscription_service + handler MercadoPago + meta_pixel_service; testes de subscription.
- **Combo na comanda/recibo** (`b4bdc70`): lista as opções escolhidas no combo "escolha N produtos" lendo `display_data['groups']`.
- **Tracking Meta** (`6c866d1`): task `send_meta_purchase_event` (com retry) + tópicos `subscription_preapproval`/`authorized_payment` no webhook.

### Infra / DB ops
- **entrypoint + scripts** (`e7494e6`): `scripts/restore_database.sh` e `scripts/resync_sequences.sh` (ressincroniza sequences após restore de dump — evita crash loop no próximo migrate); `.gitignore` passa a ignorar `.env.bak*`.

### Seeds
- **populate Ivoneth Banqueteria + seed do salad builder** (`073391a`).

> ⚠️ Pendente de deploy: migrations 0007 (whatsapp) e 0009 (agents) criam índices — rodar `migrate` no recreate; atenção à ressincronização de sequences. Flower e GlitchTip só ativam após recreate/rebuild da imagem.
