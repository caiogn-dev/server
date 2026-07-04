# Cobrança de Assinatura SaaS via PIX (mensal + anual) — Design

**Data:** 2026-07-04
**Status:** aprovado (brainstorming), aguardando revisão do spec → plano de implementação
**Repos:** server2 (backend, maior parte) + pastita-dash (tela de fatura)

## Contexto

Hoje a assinatura SaaS da Cardapidex é um **preapproval recorrente do MercadoPago (cartão)**. Na prática **ninguém pagou**: as 11 preapprovals da conta estão todas `pending`/`cancelled` (incluindo o teste de R$1, `a4dddf...`, nunca autorizado). Motivo de fundo: o público-alvo (restaurante pequeno) frequentemente **não tem/não quer cartão de crédito empresarial, mas usa PIX o dia todo** — e o MercadoPago **não permite PIX em assinatura recorrente** (preapproval exige cartão salvo pra débito automático).

Decisão: migrar a mensalidade para **fatura PIX**, entregue e cobrada pelo **WhatsApp automaticamente** (o forte da plataforma), com opção **anual com 2 meses grátis**. Objetivo primário: destravar o **1º R$ de MRR real** maximizando conversão para esse público.

A mensalidade PIX cai na **conta da plataforma Cardapidex** (token `MERCADO_PAGO_ACCESS_TOKEN` / `_sdk()` do subscription_service), **não** no gateway da loja — é receita da Cardapidex. Como hoje o usuário é dono de todas as lojas, não muda nada na prática, mas mantém a arquitetura correta para o futuro (OAuth por loja é evolução posterior, fora deste escopo).

## Decisões travadas (do brainstorming)

- **Cadência:** híbrida — mensal via WhatsApp é o centro, com oferta anual.
- **Gancho de entrada:** trial 14 dias grátis (mantém o atual `trial_ends_at`).
- **Não-pagamento** (vencido + carência esgotada): **cai pro plano Grátis** (não suspende). Loja continua vendendo, perde só recursos pagos. Retém em vez de perder.
- **Desconto anual:** 2 meses grátis (paga 10, leva 12; ~17%).
- **Merchant da mensalidade:** conta da plataforma Cardapidex.
- **Rollout:** atrás de flag `BILLING_PIX_ENABLED` (default OFF); preapproval de cartão permanece no código como opção secundária (não removido agora).

## Reúso (infra que já existe)

1. `CheckoutService.create_payment(order=None, 'pix', amount=X, store=loja)` (`apps/stores/services/checkout_service.py`, ~L1149-1275) — já gera PIX real (QR copia-e-cola + base64 + `expires_at`), com idempotência por valor.
2. `StorePayment` (`apps/stores/models/payment.py`) — já modela cobrança **sem pedido** (`order` nullable), escopada por loja, com `qr_code`, `qr_code_base64`, `ticket_url`, `external_reference`, `metadata` (JSON), estados `pending/completed/...` (pago = `completed`).
3. `CheckoutService.process_payment_webhook` + `_handle_storepayment_webhook` (checkout_service ~L1530-1633) — já reconcilia StorePayment avulso por `external_id`/`external_reference` e marca `COMPLETED`.
4. `StoreSubscription` (`apps/stores/models/subscription.py`) + `subscription_lifecycle.decide_transition` + task `enforce_subscription_lifecycle` (`apps/stores/tasks.py`) — já modelam trial→carência→dunning→suspend e aplicam `store.plan`.
5. `billing.PLAN_CATALOG` (`apps/stores/billing.py`) — catálogo/limites/feature-gates.
6. Dash: bloco de **QR + copia-e-cola** em `OrderDetailContent.tsx` (~L826-866) e o "Copiar" de `PaymentLinkPage.tsx` — reaproveitar para a fatura SaaS.

## Arquitetura

### 1. Modelo de dados (mínimo)
Sem modelo novo pesado. **A fatura = um `StorePayment`** (`order=None`, `store=loja`, `payment_method=pix`) etiquetado:
- `external_reference = f"subpix:{subscription_id}:{period_key}"` (period_key = `YYYY-MM` para mensal, `YYYY` para anual)
- `metadata = { kind: 'monthly'|'annual', period_start, period_end, subscription_id }`

`StoreSubscription` ganha um campo novo: `billing_cycle` (`monthly`|`annual`, default `monthly`). Histórico de faturas = query de `StorePayment` da loja com `external_reference` começando em `subpix:`. (StoreInvoice dedicado é possível no futuro; YAGNI agora.)

### 2. Serviço novo: `apps/stores/services/pix_billing_service.py`
- `generate_invoice(subscription) -> StorePayment` — monta o PIX **com o token da plataforma** (reusa `subscription_service._sdk()`), cria/retorna o `StorePayment` etiquetado com o valor do plano (mensal ou anual = mensal×10). **Idempotente por período**: se já existe fatura `pending`/`completed` do mesmo `period_key`, retorna ela. Reaproveita o payload PIX do `CheckoutService` (extrair o trecho de montagem do `payment_method_id=pix` para uma função compartilhada, evitando duplicar).
- `apply_invoice_paid(store_payment)` — chamado quando a fatura vira `COMPLETED`: renova `current_period_end` (+1 mês ou +12 meses conforme `billing_cycle`), zera `dunning_since`/`grace_until`, transiciona `past_due`/`trialing`→`active`, garante `store.plan = subscription.plan`. **É o elo que hoje não existe** (PIX pago não avança a assinatura).
- Guard de isenção: `is_billing_exempt(store)` → nunca gera fatura (as 4 lojas reais permanecem intocadas).

### 3. Geração automática + ciclo (task)
Estender `enforce_subscription_lifecycle` (`apps/stores/tasks.py`), gated por `BILLING_PIX_ENABLED`:
- Para cada assinatura não-isenta com `current_period_end` (ou fim de trial) a **≤3 dias**: chama `generate_invoice` e dispara o envio (seção 4).
- Lifecycle continua decidindo status; o gatilho de "pagou" passa a ser **fatura PIX COMPLETED** (via webhook), não preapproval.
- Transição de não-pagamento passa a `downgrade_free` (ver seção 6).

### 4. Entrega + lembretes via WhatsApp (motor de conversão)
Reusa a automação de WhatsApp (envio de mensagem por loja). Sequência automática por fatura (idempotente — não reenvia o mesmo passo):
- **D-3 do vencimento:** "Sua mensalidade Cardapidex está pronta 👇" + copia-e-cola PIX + valor + vencimento.
- **D0:** lembrete "vence hoje".
- **D+2 / D+5 (carência/dunning):** "ainda dá tempo, seu site continua no ar" + PIX.
- **Ao pagar (webhook):** confirmação instantânea "Recebido! Obrigado 🎉 renovado até {data}".

Sempre com **copia-e-cola** (funciona em qualquer app de banco, sem cartão). Fallback: e-mail + fatura sempre visível no painel. Os textos e os dias são parametrizáveis (constantes no serviço).

### 5. Plano anual (2 meses grátis)
- Catálogo (`/public/plans/`) passa a expor, por plano pago, o preço anual = `monthly_price × 10`.
- No painel e no WhatsApp: oferta "economize 2 meses no anual".
- 1 PIX único; ao pagar (`kind='annual'`), `current_period_end = +12 meses`. Zero cobrança no restante do ano.

### 6. Não-pagamento → cai pro Grátis
Ajustar `subscription_lifecycle.decide_transition`: fatura vencida + carência esgotada retorna **`downgrade_free`** (hoje já é o caminho do trial vencido) em vez de `suspend`. A loja continua vendendo; `store.plan` volta pra `free` (perde domínio/bot/limites). WhatsApp: "voltamos você pro Grátis; quando quiser, é só pagar pra reativar o Pro". (`suspend` deixa de ser acionado pelo fluxo normal de billing; permanece disponível para casos manuais/abuso.)

### 7. Dash — tela de fatura (`pastita-dash`)
- `src/services/billing.ts`: novas funções `getCurrentInvoice(slug)`, `listInvoices(slug)`, `setBillingCycle(slug, 'monthly'|'annual')`; tipo `Invoice { id, amount, status, kind, period_start, period_end, due_date, pix_code, pix_qr_code, paid_at }`. `subscribe`/`changePlan` passam a retornar/abrir a **fatura PIX** em vez de `init_point` de cartão.
- Componente reutilizável `PixInvoicePanel` (extrai o markup hoje duplicado em `OrderDetailContent`/`PaymentLinkPage`): QR base64 + copia-e-cola com "Copiar" + valor + vencimento + badge (pago/pendente/expirado).
- `/assinatura` (`SubscriptionManagementPage`): mostra a fatura atual (PixInvoicePanel), toggle **mensal/anual**, e **histórico de faturas**. Polling/refetch do status (pago via webhook; dash faz refetch periódico de `getCurrentInvoice`).
- `TrialBanner.tsx`: adicionar caso "fatura em aberto/vencendo" com CTA → `/assinatura`.
- Cleanup: remover textos de "cartão/placeholder/em breve" desatualizados.
- Endpoint DRF novo: `GET /stores/{slug}/invoices/` (lista) e `GET /stores/{slug}/invoices/current/` (fatura vigente, gera se faltar e dentro da janela). Ajustar `StorePaymentViewSet.get_queryset` para incluir `Q(store=...)` (avulsas), destravando também a Fase 3b.

### 8. Fluxo de dados (feliz)
```
Trial acaba em ≤3d
  → task: generate_invoice(sub) → StorePayment PIX (token plataforma, subpix:{id}:{YYYY-MM})
  → WhatsApp: "sua fatura 👇" + copia-e-cola
Dono paga o PIX no app do banco
  → MP → webhook /webhooks/payments/mercadopago/
  → process_payment_webhook → _handle_storepayment_webhook → StorePayment.COMPLETED
  → apply_invoice_paid: current_period_end += 1 mês; status=active; store.plan=sub.plan
  → WhatsApp: "recebido! renovado até {data}"
Painel /assinatura: fatura vira "paga"; próxima fatura só no fim do período.
```

## Error handling
- **Idempotência de fatura:** `generate_invoice` não cria 2 faturas do mesmo `period_key` (reusa `pending`/`completed`).
- **Idempotência de webhook:** já existe (cache `mp_webhook:{id}:{status}` + `StorePaymentWebhookEvent` unique).
- **Idempotência de envio WhatsApp:** cada passo (D-3/D0/D+2/D+5/pago) marcado em `metadata` da fatura pra não reenviar.
- **Falha ao gerar PIX no MP:** loga, não quebra a task; tenta no próximo tick; nunca deixa a loja sem acesso por erro de billing (fail-open no acesso).
- **Loja isenta:** guard em `generate_invoice` e no lifecycle — nunca cobra as 4 reais.
- **PIX expirado sem pagar:** dentro da carência, regenera na próxima fatura/lembrete; após carência, `downgrade_free`.

## Testing (TDD, Iron Law)
- `pix_billing_service.generate_invoice`: cria StorePayment PIX com token plataforma, etiqueta correta, idempotente por período, respeita isenção.
- `apply_invoice_paid`: renova período (mensal +1 / anual +12), zera dunning/grace, `past_due→active`, aplica `store.plan`; isenta ignorada.
- `decide_transition`: vencido+carência → `downgrade_free` (não `suspend`); regressão do fluxo trial.
- Webhook ponta-a-ponta: StorePayment `subpix:` COMPLETED → assinatura avança (integração com `process_payment_webhook`).
- Envio WhatsApp: cada passo dispara 1x (idempotente), com copia-e-cola correto.
- Dash: `PixInvoicePanel` (copia-e-cola + estados), `getCurrentInvoice`/`listInvoices`.
- Smoke ponta-a-ponta em prod na `testezaco` (não-isenta) com valor baixo antes de ligar a flag.

## Fora de escopo (YAGNI agora)
- OAuth/split por loja (mensalidade continua na conta da plataforma).
- Modelo `StoreInvoice` dedicado (usa StorePayment etiquetado).
- Débito automático PIX recorrente (MP "PIX automático") — pode ser fase futura; por ora é fatura + lembrete.
- Remoção do preapproval de cartão (fica como opção secundária).

## Levers de conversão (resumo)
WhatsApp entrega+lembra+confirma · copia-e-cola sem cartão · cai pro Grátis (não perde a loja) · anual com 2 meses grátis · trial 14d mantido · fatura sempre à mão no painel.
