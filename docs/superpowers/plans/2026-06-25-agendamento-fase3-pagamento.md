# Plano — Agendamento Fase 3: Link de pagamento / cobrança (painel)

> Gerado 2026-06-25. Pré-requisito: Fases 1+2 já no ar. Ver memory/project_agendamento_roadmap.md
> e docs/ESTADO_ATUAL_2026-06-25.md (no WORK).
> **NÃO começar a codar antes de fechar as 5 decisões da seção 2.**

## 1. Estado atual (fatos do código)

**Backend (server2, branch `development`):**
- `generate_payment` — `apps/stores/api/views/order_views.py:534`. `POST /stores/orders/{id}/generate_payment/`. Chama `CheckoutService.create_payment(order, payment_method, payment_data)`; devolve `{ payment, order }`.
- `CheckoutService.create_payment` — `apps/stores/services/checkout_service.py:1033`. Integra MercadoPago SDK. Para PIX grava direto no StoreOrder: `pix_code` (copia-e-cola), `pix_qr_code` (base64), `pix_ticket_url`, `pix_expires_at`, `payment_id`, `payment_status=PENDING`. **NÃO cria `StorePayment`.**
- `StoreOrder` — `apps/stores/models/order.py:20`. Pagamento é **single-charge**: `payment_method`, `payment_id` (1 valor), `payment_preference_id`, `pix_*`, `paid_at`. **NÃO existe `amount_paid`.** `total` decimal 2 casas.
- `StorePayment` — `apps/stores/models/payment.py:114`. **Já modelado para múltiplos pagamentos por pedido** (`order=FK(related_name='payments')`, `amount`, `status`, `external_id`, `qr_code`, `qr_code_base64`, `ticket_url`, `paid_at`, `refunded_amount`). Tem `sync_to_order()` (~288) que espelha PIX/paid_at no order. **Peça-chave da Fase 3, já existe.**
- `PaymentService.create_payment` — `apps/stores/services/payment_service.py:30`. Cria `StorePayment` mas é caminho separado, sem a integração MP do CheckoutService.
- Webhook — `process_payment_webhook(payment_id, status)` (`checkout_service.py:1271`) casa por `StoreOrder.payment_id` (único) e seta `PAID`+`paid_at`. **Single-charge: 2ª cobrança sobrescreveria `order.payment_id`.** Entrada: `apps/stores/api/webhooks.py:213` (dedup `mp_webhook:{id}:{status}` em :207).
- `adjust` — `order_views.py:261`. **Já existe**, recalcula `total` via `recalculate_totals`, bloqueia cancelled/refunded/failed, não toca pagamento (groundwork Fase 4).
- `StorePaymentViewSet.by_order` — `apps/stores/api/payment_views.py:262` → `GET /stores/payments/by_order/?order_id=`.

**Frontend (pastita-dash):**
- `OrderDetailPage.tsx` — já chama `paymentsService.getByOrder` (~315) e renderiza `payments[]`+`pix_code`+`paymentLink` num `<details>` (645-692). **Lista vem vazia hoje** (generate_payment não cria StorePayment). Sem "falta receber".
- `ordersService.generatePayment` — `src/services/orders.ts:156` (existe).
- `paymentsService` — `src/services/payments.ts` (getByOrder/createPayment/refundPayment existem).
- `EditOrderDrawer.tsx` — Fase 2; chama `adjustOrder`+`updateOrder`; **sem lógica de cobrança da diferença.**
- Tipos — `Order` (`src/types/index.ts:330+`) tem pix_* mas **não `amount_paid`**. `Payment` type existe (:427).

## 2. Decisões — TRAVADAS pelo usuário 2026-06-25
1. ✅ **Arquitetura: Opção A.** `StorePayment` é a fonte da verdade das cobranças. `generate_payment` cria StorePayment; webhook casa por `external_id`; `amount_paid = SUM(payments completed)`; `order.pix_*` = espelho da cobrança ativa (compat storefront/OrderPrint/bot). Suporta N cobranças nativo. Risco: webhook (prod cobra de verdade) → fallback legado obrigatório.
2. ✅ **`amount_paid` DERIVADO** (SerializerMethodField/annotation, soma dos payments `completed`, zero drift). Denormaliza depois se ficar lento.
3. ✅ **Só PIX, MANUAL e OPCIONAL.** O usuário decide se gera o link ou não e **escolhe o valor** (não força o amount_due). Cartão fica pra depois.
4. ✅ **NOVO ESCOPO — Link de pagamento AVULSO (feature à parte):** além de cobrança vinculada a pedido, gerar **link de pagamento de valor arbitrário SEM pedido** (ex: cobrar um cliente um valor qualquer). Implica `StorePayment.order` NULLABLE (ou conceito de cobrança avulsa). Ver seção 2b.
5. ✅ **Corte Fase 3 = mecanismo MANUAL.** Endpoint cobrança valor arbitrário + UI "falta receber R$ X" + botão "gerar cobrança/link PIX" (no pedido E avulso). Gatilho AUTOMÁTICO ao editar item pago → Fase 4.
6. ✅ **Idempotência:** reusar StorePayment PENDING não-expirada ao gerar PIX 2x (não duplica). Status do order: usar fluxo existente — order só vira `paid` quando `amount_paid >= total`; não criar status "partially_paid" novo no 1º corte (avaliar `processing` se precisar sinalizar parcial).

## 2b. Link de pagamento avulso (decisão 4) — desenho
- `StorePayment.order` passa a ser **nullable** (migration) OU criar tela/endpoint dedicado que cria StorePayment sem order, escopado por loja (`store` FK obrigatório). Cobrança avulsa = StorePayment(order=null, store=X, amount=livre, description, status, external_id MP, qr_code, ticket_url).
- **Frontend: feature própria** (não só dentro de Pedidos) — ex. página/menu "Cobranças" ou "Link de pagamento" no painel: input de valor + descrição → gera PIX copia-e-cola + link compartilhável. Listar cobranças avulsas + status.
- Webhook: mesma rota; casa StorePayment por external_id independente de ter order. Se `order` é null, só marca a cobrança como paga (não há order pra sincronizar).
- **A FAZER:** confirmar se a página avulsa entra JÁ na Fase 3 ou vira "Fase 3b". Recomendo backend unificado (order nullable) na Fase 3 + UI avulsa logo em seguida.

## 3. Contratos alvo (frontend ↔ backend)
- `StoreOrderSerializer` +read-only: `amount_paid` (derivado), `amount_due` (=total-amount_paid), opc `is_fully_paid`.
- `generate_payment` aceita `amount` opc no body (default = `amount_due`, NÃO `total`) → cria StorePayment + retorna `payment{pix_code,pix_qr_code,ticket_url,amount,payment_db_id}`.
- `GET /stores/payments/by_order/?order_id=` (existe) passa a ter dados reais.
- Front: botão "Gerar cobrança PIX (R$ X faltante)" + banner "Falta receber R$ X" no OrderDetailPage.

## 4. Tasks TDD (backend primeiro)
**Backend:**
- **B1** — `amount_paid`/`amount_due` no StoreOrder + serializer (derivado). Teste: 0 payments→0/total; 1 completed X→X/(total-X); pending não conta. Arqs: `models/order.py`, `api/serializers.py`, queryset em `order_views.py` (annotation anti-N+1).
- **B2** — `create_payment` cria StorePayment (PIX) + aceita `amount`. Teste: mock SDK MP cria 1 StorePayment(pending,amount=amount_due,external_id,qr_code,ticket_url); order.pix_* segue espelhado; 2x não duplica PENDING válida. Arq: `checkout_service.py`.
- **B3** — `generate_payment` aceita `amount` + regra "já pago". Teste: paid c/ amount_due=0→400; com diferença→cobra diferença; cancelled→bloqueado. Arq: `order_views.py`.
- **B4** — webhook casa por `StorePayment.external_id` (multi-charge) + fallback legado. Teste: approved p/ external_id marca AQUELA StorePayment=completed, recalcula amount_paid; order vira paid só quando amount_paid>=total; cobrança antiga intacta; fallback external_id legado por order.payment_id preservado. Arqs: `checkout_service.py`, `webhooks.py`. **CAMINHO SENSÍVEL — testes de regressão fortes + idempotência.**

**Frontend:**
- **F1** — tipos `Order.amount_paid/amount_due` + `generatePayment(orderId,{amount?,payment_method?})`. Teste em orders.service.test.
- **F2** — banner "Falta receber R$ X" no OrderDetailPage (amount_due>0) / "Pago integralmente" (=0). RTL.
- **F3** — botão "Gerar cobrança PIX (diferença)" + copia-e-cola/QR/link (reusa `<details>` existente + copia-e-cola de CustomerSessionsPage:447). RTL.
- **F4** — lista de cobranças por pedido (getByOrder já chamado) renderiza todas com amount/status. RTL 2 payments.
- **F5 (opc/bridge Fase4)** — em EditOrderDrawer, pedido pago + edição muda total → aviso "gerará cobrança de R$ X" (sem disparar). Confirmar se entra na 3.

## 5. Sequência
B1→B2→B3→B4 (cada um mergeável). F1 dep B1/B3; F2 dep B1; F3 dep B2/B3; F4 dep B2/B4. Backend deploya antes do front (campos aditivos retrocompatíveis).

## 6. Riscos
- B4 webhook = crítico (prod cobra de verdade desde 17/jun). Fallback legado + idempotência (MP reenvia; dedup existe).
- `order.pix_*` lido por storefront/OrderPrint/bot → manter como espelho, não remover.
- Decimais: Decimal/quantize 2 casas (MP rejeita transaction_amount mal-quantizado; tratamento em checkout_service.py:804).

## Arquivos-chave
- server2: `apps/stores/services/checkout_service.py`, `apps/stores/api/views/order_views.py`, `apps/stores/models/order.py`, `apps/stores/models/payment.py`, `apps/stores/api/serializers.py`, `apps/stores/api/webhooks.py`
- pastita-dash: `src/pages/orders/OrderDetailPage.tsx`, `src/services/orders.ts`, `src/services/payments.ts`, `src/components/.../EditOrderDrawer.tsx`
