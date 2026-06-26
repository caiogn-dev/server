# EVOLUCAO_SERVER.md — Backlog e Histórico do Backend `server`

> Atualizado automaticamente pelo loop diário. Branch trunk: `development`.
> Regra: nunca recriar fix já presente em `development`. Confirmar via `git log` antes de propor.

---

## Estado da Suíte de Testes (2026-06-26)

Executado com `pytest --no-migrations` (SQLite local, sem Docker):

- **332 passando, 6 falhando pré-existentes** (não introduzidos por este loop):
  - `test_create_payment_storepayment.py` — 4 falhas (mock de MercadoPago não configurado em ambiente local)
  - `test_checkout_menu_invalidation.py` — 2 falhas (cache de menu/agente — requer Redis)
  - Nota: `AddIndexConcurrently` em `agents/0009` falha com SQLite; contornado com `--no-migrations`.

---

## Já feito em `development` (últimos commits)

| Data | Fix | Prioridade |
|------|-----|------------|
| 2026-06-25 | Criptografia de tokens do MessengerAccount em repouso (EncryptedCharField) | P0 |
| 2026-06-25 | Validação anti-SSRF em URLs de StoreWebhook | P0 |
| 2026-06-25 | Auth e tenant check nas views de delivery Uber | P0 |
| 2026-06-25 | Bloqueio de open redirect no login do painel | P0 |
| 2026-06-25 | SSE: autenticação via ticket de uso único (sem token permanente na query string) | P0 |
| 2026-06-25 | mark_paid/update_payment_status: select_for_update, paid_at idempotente, PIX expirado bloqueado | P1 |
| 2026-06-25 | Migration CustomerSession (delivery_method/delivery_address/payment_method) | P2 |
| 2026-06-25 | Fase 3: StorePayment como fonte da verdade, link de pagamento avulso, webhook multi-charge | P1 |
| 2026-06-25 | IDOR: subscribe_conversation nos consumers WS (WhatsApp + Handover) | P0 |
| 2026-06-25 | IDOR: send_* do WhatsApp (ownership da conta) | P0 |
| 2026-06-25 | IDOR: Marketing (import_csv, stats, send_coupon, etc.) | P0 |
| 2026-06-25 | IDOR: Campaigns (ações de detalhe, account_id) | P0 |
| 2026-06-25 | IDOR: ReportScheduleViewSet (account/company) | P0 |
| 2026-06-25 | IDOR: CompanyProfile (store_data/create) | P0 |
| 2026-06-25 | IDOR: HandoverViewSet (cross-tenant) | P0 |

---

## Feito neste loop (2026-06-26)

### PR aberto: `bot/server-2026-06-26-coupon-validate-idor`

**Problema duplo em `StoreCouponViewSet.validate()`:**

1. **IDOR (P1)** — a action `validate` chamava `StoreCoupon.objects.get()` diretamente,
   sem respeitar o escopo de loja do usuário autenticado. Qualquer usuário autenticado
   (staff da Loja A) conseguia inspecionar/validar cupons de qualquer outra loja.

2. **Atributos inexistentes (P1/bug)** — a action referenciava `coupon.max_uses` e
   `coupon.min_order_value`, mas o modelo usa `usage_limit` e `min_purchase`. Isso
   causava `AttributeError` → HTTP 500 ao tentar validar qualquer cupom com limite de uso.

**Fix:** usar `self.get_queryset()` (tenant-scoped) no lugar de `StoreCoupon.objects`,
e delegar a validação ao método `coupon.is_valid()` do próprio modelo — que usa os
nomes corretos de campo.

**Cobertura TDD:** 5 novos testes em `test_coupon_validate_idor.py` (IDOR, happy path,
auth, 400, AttributeError).

---

## Backlog Priorizado (próximos itens)

### P0 — Segurança crítica

- [ ] **WhatsApp webhook: bypass DEBUG** — `webhooks/views.py:105` ainda continua
  (com warning) ao receber assinatura inválida se `DEBUG=True`. Em produção está
  protegido, mas ambiente de staging/CI pode ser explorado se `DEBUG=True` vazar.
  Fix: rejeitar sempre, independente de DEBUG.

- [ ] **WebSocket token TTL** — `get_cached_user()` não verifica `token.created`.
  Tokens muito antigos (ex: 1 ano) continuam válidos para WS indefinidamente.
  Fix: checar idade do token; rejeitar se > threshold configurável.

### P1 — Bugs de produção

- [ ] **6 testes pré-existentes falhando** — `test_create_payment_storepayment` (4)
  e `test_checkout_menu_invalidation` (2). Requerem diagnóstico mais aprofundado
  (mock de MP + configuração de Redis local).

- [ ] **WhatsApp phone lookup `icontains`** — `MessageViewSet` usa `icontains` em vez
  de match exato (`iexact` ou `=`). Busca por `+5563` retorna mensagens de qualquer
  número que contenha essa sequência. PR #276 aberto.

### P2 — Performance / DX

- [ ] **N+1 em endpoint de conversas do agente** — PR #267 aberto (prefetch_related).

### Acúmulo de PRs

Há ~100 PRs abertos. Muitos são duplicatas de fixes já mergeados em `development`.
Recomendação: fechar manualmente os PRs cujos fixes já estão em `development` (ver
tabela "Já feito" acima) para limpar a fila.
