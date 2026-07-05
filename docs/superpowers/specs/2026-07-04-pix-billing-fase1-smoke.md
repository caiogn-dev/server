# Fase 1 PIX Billing — Notas de Smoke (manual)

Status do código: **8/8 tasks completas, na branch `development`, gated por `BILLING_PIX_ENABLED` (default `false`) → deploy é no-op.**

Suíte de billing (verificada 05/jul, 70/70 verde):
```
docker compose exec -T web python manage.py test \
  apps.stores.tests.test_pix_billing \
  apps.stores.tests.test_subscription_lifecycle \
  apps.stores.tests.test_subscription_lifecycle_fields \
  apps.stores.tests.test_enforce_subscription_task \
  apps.stores.tests.test_billing \
  apps.stores.tests.test_subscription \
  apps.stores.tests.test_subscription_management -v 1
```
Nota: discovery do pacote inteiro (`apps.stores.tests`) tem bug PRÉ-EXISTENTE no test-loader (não deste trabalho) — rodar módulos nomeados como acima.

## Smoke manual (precisa de pagamento PIX real — só o Caio faz)

Pré: `BILLING_PIX_ENABLED=true` **só em ambiente de teste** (nunca ligar em prod sem revisão final). Loja NÃO-isenta (`testezaco`, ou criar uma com `billing_exempt=False`).

1. **Gerar fatura**: no shell, `pix_billing_service.generate_invoice(sub)` para a assinatura da loja de teste. Confirma que cria um `StorePayment` com `external_reference` começando em `subpix:{sub_id}:{period_key}`, status `PENDING`, `qr_code`/`qr_code_base64` preenchidos, na conta da PLATAFORMA (token `_sdk()`).
   - Alternativa via API: `GET /api/v1/stores/testezaco/invoices/current/` (gera idempotente e retorna o dict com `pix_code`/`pix_qr_code`).
2. **Idempotência**: chamar de novo — NÃO cria segunda fatura no mesmo período.
3. **Pagar o PIX** com valor baixo (ajustar plano de teste p/ centavos, ou pagar o valor cheio e estornar depois).
4. **Webhook**: confirmar que o webhook de pagamento do MP chega, `process_payment_webhook` reconhece o `subpix:` e chama `apply_invoice_paid`:
   - `sub.status` → `ACTIVE`
   - `sub.current_period_end` renovado (+1 mês mensal / +12 anual)
   - `store.plan` aplicado
   - dunning/grace limpos, `downgraded_for_nonpayment=False`
5. **Não-pagamento** (opcional, mais demorado): deixar vencer + dunning esgotar → `enforce_subscription_lifecycle` cai a loja pro `free` com `downgraded_for_nonpayment=True` (aviso no dash — Fase 3).
6. **Reverter** o ambiente de teste: `BILLING_PIX_ENABLED=false`, estornar pagamento, restaurar plano da loja de teste.

## Fora da Fase 1 (planos próprios)
- **Fase 2**: automação WhatsApp das faturas (D-3/D0/D+2/D+5/pago) — seção 4 do design.
- **Fase 3**: tela de fatura + aviso de reativação no dash — seção 7 do design + campo `downgraded_for_nonpayment`.
