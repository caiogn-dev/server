# PIX Billing — Fase 1 (núcleo backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar fatura mensal/anual de assinatura via PIX (na conta da plataforma), reconciliar o pagamento e avançar a assinatura, com não-pagamento caindo pro Grátis — tudo atrás de flag.

**Architecture:** A fatura é um `StorePayment` avulso (`order=None`, `store=loja`, `payment_method=pix`) etiquetado `external_reference=subpix:{sub_id}:{period_key}`. Um serviço novo `pix_billing_service` gera a fatura com o token da PLATAFORMA (reusa `subscription_service._sdk()`) e avança a `StoreSubscription` quando o webhook marca a fatura `COMPLETED`. O lifecycle passa a cair pro Grátis (não suspender) na inadimplência.

**Tech Stack:** Django 4 + DRF, Celery, PostgreSQL, SDK `mercadopago`. Testes Django em container.

## Global Constraints

- Branch única de avanço do server2: `development`. Fetch+reconciliar antes de push.
- TDD Iron Law: escrever teste, ver RED, código mínimo pro GREEN, zero regressão.
- Mensagens de commit em português.
- Toda cobrança de assinatura usa o token da **plataforma** (`subscription_service._sdk()`), nunca o gateway da loja.
- Loja isenta (`billing.is_billing_exempt(store)`) NUNCA é cobrada — guard obrigatório em toda geração/aplicação.
- Tudo gated por `settings.BILLING_PIX_ENABLED` (default `False`) — deploy é no-op até go-live.
- Estados: `StorePayment` pago = `PaymentStatus.COMPLETED` (não existe "paid"). `StoreSubscription.Status` ∈ trialing/active/past_due/suspended/canceled.
- Rodar teste: `docker compose exec -T web python manage.py test <caminho> -v 2` (sem python local; container + Postgres).

---

### Task 1: Campo `billing_cycle` + razão do downgrade em StoreSubscription

**Files:**
- Modify: `apps/stores/models/subscription.py`
- Create (migration): `apps/stores/migrations/00XX_subscription_billing_cycle.py` (via makemigrations)
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Produces: `StoreSubscription.billing_cycle` (`'monthly'|'annual'`, default `'monthly'`); `StoreSubscription.downgraded_for_nonpayment` (bool, default False).

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py
from django.test import TestCase
from apps.stores.models import Store, StoreSubscription

class BillingCycleFieldTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Loja Teste", slug="loja-teste")

    def test_subscription_defaults_monthly_and_not_downgraded(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        self.assertEqual(sub.billing_cycle, "monthly")
        self.assertFalse(sub.downgraded_for_nonpayment)

    def test_billing_cycle_accepts_annual(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro", billing_cycle="annual")
        self.assertEqual(sub.billing_cycle, "annual")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.BillingCycleFieldTest -v 2`
Expected: FAIL (`billing_cycle` inexistente / erro de atributo ou coluna).

- [ ] **Step 3: Add the fields**

```python
# apps/stores/models/subscription.py — dentro da classe StoreSubscription
class BillingCycle(models.TextChoices):
    MONTHLY = "monthly", "Mensal"
    ANNUAL = "annual", "Anual"

billing_cycle = models.CharField(
    max_length=10, choices=BillingCycle.choices, default=BillingCycle.MONTHLY
)
# Distingue quem caiu pro Grátis por inadimplência (mostra aviso) de quem
# escolheu o Grátis.
downgraded_for_nonpayment = models.BooleanField(default=False)
```

- [ ] **Step 4: Make + run migration, run test**

Run: `docker compose exec -T web python manage.py makemigrations stores`
Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.BillingCycleFieldTest -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/stores/models/subscription.py apps/stores/migrations/ apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): billing_cycle + downgraded_for_nonpayment na assinatura"
```

---

### Task 2: `pix_billing_service.generate_invoice` — gera fatura PIX na conta da plataforma

**Files:**
- Create: `apps/stores/services/pix_billing_service.py`
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Consumes: `subscription_service._sdk()` (SDK MP da plataforma), `billing.get_plan(plan_key)`, `billing.is_billing_exempt(store)`, `StorePayment`, `StoreSubscription.billing_cycle`.
- Produces: `generate_invoice(subscription, now=None) -> StorePayment | None`. Retorna `None` se isenta. Cria `StorePayment` PIX com `external_reference=f"subpix:{sub.id}:{period_key}"`, `metadata={kind, period_start, period_end, subscription_id, sent_steps: []}`, `amount` = mensal ou mensal×10 (anual). Idempotente por `period_key` (reusa `pending`/`completed`). `period_key` = `YYYY-MM` (monthly) ou `YYYY` (annual), derivado de `now`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py — nova classe
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone as dtz
from apps.stores.models import StorePayment
from apps.stores.services import pix_billing_service

def _fake_pix_sdk():
    sdk = MagicMock()
    sdk.payment.return_value.create.return_value = {
        "status": 201,
        "response": {
            "id": 999001,
            "point_of_interaction": {"transaction_data": {
                "qr_code": "PIXCOPIACOLA123",
                "qr_code_base64": "AAAABBBB==",
                "ticket_url": "https://mp/ticket/999001",
            }},
        },
    }
    return sdk

class GenerateInvoiceTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Loja X", slug="loja-x", plan="pro")
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        self.now = datetime(2026, 7, 4, tzinfo=dtz.utc)

    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_generates_monthly_pix_invoice(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        inv = pix_billing_service.generate_invoice(self.sub, now=self.now)
        self.assertIsNotNone(inv)
        self.assertEqual(inv.payment_method, StorePayment.PaymentMethod.PIX)
        self.assertEqual(inv.store_id, self.store.id)
        self.assertIsNone(inv.order_id)
        self.assertEqual(inv.external_reference, f"subpix:{self.sub.id}:2026-07")
        self.assertEqual(inv.qr_code, "PIXCOPIACOLA123")
        self.assertEqual(float(inv.amount), 249.0)  # pro mensal
        self.assertEqual(inv.metadata["kind"], "monthly")

    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_annual_is_ten_times_monthly(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        self.sub.billing_cycle = "annual"; self.sub.save()
        inv = pix_billing_service.generate_invoice(self.sub, now=self.now)
        self.assertEqual(float(inv.amount), 2490.0)
        self.assertEqual(inv.external_reference, f"subpix:{self.sub.id}:2026")

    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_idempotent_per_period(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        a = pix_billing_service.generate_invoice(self.sub, now=self.now)
        b = pix_billing_service.generate_invoice(self.sub, now=self.now)
        self.assertEqual(a.id, b.id)
        self.assertEqual(StorePayment.objects.filter(store=self.store).count(), 1)

    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_exempt_store_never_charged(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        self.store.billing_exempt = True; self.store.save()
        self.assertIsNone(pix_billing_service.generate_invoice(self.sub, now=self.now))
        self.assertEqual(StorePayment.objects.filter(store=self.store).count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.GenerateInvoiceTest -v 2`
Expected: FAIL (`pix_billing_service` inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# apps/stores/services/pix_billing_service.py
"""Cobrança de assinatura SaaS via PIX (fatura mensal/anual).

A fatura é um StorePayment avulso (order=None) cobrado na conta da PLATAFORMA
(subscription_service._sdk()), não no gateway da loja. Reconciliação e ciclo
de vida reaproveitam a infra existente. Ver docs/superpowers/specs/2026-07-04-pix-monthly-billing-design.md
"""
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from apps.stores import billing
from apps.stores.models import StorePayment, StoreSubscription
from apps.stores.services import subscription_service

logger = logging.getLogger(__name__)

ANNUAL_MONTHS_CHARGED = 10  # paga 10, leva 12 (2 meses grátis)


def _period_key(subscription, now):
    if subscription.billing_cycle == StoreSubscription.BillingCycle.ANNUAL:
        return now.strftime("%Y")
    return now.strftime("%Y-%m")


def _invoice_amount(plan, cycle):
    monthly = Decimal(str(plan["monthly_price"]))
    if cycle == StoreSubscription.BillingCycle.ANNUAL:
        return monthly * ANNUAL_MONTHS_CHARGED
    return monthly


def generate_invoice(subscription, now=None):
    """Gera (ou retorna a existente) a fatura PIX do período atual. None se isenta."""
    store = subscription.store
    if billing.is_billing_exempt(store):
        return None
    now = now or timezone.now()
    period_key = _period_key(subscription, now)
    ext_ref = f"subpix:{subscription.id}:{period_key}"

    existing = StorePayment.objects.filter(
        store=store, external_reference=ext_ref,
        status__in=[StorePayment.PaymentStatus.PENDING, StorePayment.PaymentStatus.COMPLETED],
    ).first()
    if existing:
        return existing

    plan = billing.get_plan(subscription.plan)
    amount = _invoice_amount(plan, subscription.billing_cycle)
    kind = "annual" if subscription.billing_cycle == StoreSubscription.BillingCycle.ANNUAL else "monthly"

    sdk = subscription_service._sdk()
    resp = sdk.payment().create({
        "transaction_amount": float(amount),
        "payment_method_id": "pix",
        "description": f"Cardapidex {plan['name']} — {store.name} ({kind})",
        "payer": {"email": getattr(store, "owner_email", None) or f"{store.slug}@cardapidex.com.br"},
        "external_reference": ext_ref,
        "notification_url": f"{getattr(settings, 'BACKEND_URL', '').rstrip('/')}/webhooks/payments/mercadopago/",
    })
    if resp.get("status") not in (200, 201):
        logger.error("Falha ao gerar PIX de assinatura p/ %s: %s", store.slug, resp)
        raise RuntimeError(f"MercadoPago recusou o PIX da fatura: {resp.get('status')}")
    body = resp["response"]
    tx = (body.get("point_of_interaction") or {}).get("transaction_data") or {}

    return StorePayment.objects.create(
        store=store, order=None,
        amount=amount, currency="BRL",
        payment_method=StorePayment.PaymentMethod.PIX,
        status=StorePayment.PaymentStatus.PENDING,
        external_id=str(body.get("id", "")),
        external_reference=ext_ref,
        qr_code=tx.get("qr_code", ""),
        qr_code_base64=tx.get("qr_code_base64", ""),
        ticket_url=tx.get("ticket_url", ""),
        expires_at=now + timezone.timedelta(days=3),
        metadata={
            "kind": kind, "subscription_id": subscription.id,
            "period_key": period_key, "sent_steps": [],
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.GenerateInvoiceTest -v 2`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/pix_billing_service.py apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): pix_billing_service.generate_invoice (fatura PIX mensal/anual)"
```

---

### Task 3: `apply_invoice_paid` — avança a assinatura quando a fatura é paga

**Files:**
- Modify: `apps/stores/services/pix_billing_service.py`
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Consumes: `StorePayment` (a fatura `COMPLETED`), `StoreSubscription`, `billing.is_billing_exempt`.
- Produces: `apply_invoice_paid(store_payment) -> dict`. Renova `current_period_end` (+1 mês monthly / +12 meses annual, a partir de `max(now, current_period_end)`), `status=ACTIVE`, zera `dunning_since`/`grace_until`, `downgraded_for_nonpayment=False`, `store.plan = subscription.plan`. Idempotente (fatura já aplicada não renova 2x — marca `metadata['applied']=True`).

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py — nova classe
from dateutil.relativedelta import relativedelta  # já usado no projeto? senão usar timedelta(days=30/365)

class ApplyInvoicePaidTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Loja Y", slug="loja-y", plan="free")
        self.sub = StoreSubscription.objects.create(
            store=self.store, plan="pro", status=StoreSubscription.Status.PAST_DUE,
            dunning_since=timezone.now(), downgraded_for_nonpayment=True,
        )
        self.inv = StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_reference=f"subpix:{self.sub.id}:2026-07",
            metadata={"kind": "monthly", "subscription_id": self.sub.id},
        )

    def test_paid_invoice_activates_and_applies_plan(self):
        pix_billing_service.apply_invoice_paid(self.inv)
        self.sub.refresh_from_db(); self.store.refresh_from_db()
        self.assertEqual(self.sub.status, StoreSubscription.Status.ACTIVE)
        self.assertIsNone(self.sub.dunning_since)
        self.assertFalse(self.sub.downgraded_for_nonpayment)
        self.assertEqual(self.store.plan, "pro")
        self.assertIsNotNone(self.sub.current_period_end)

    def test_apply_is_idempotent(self):
        pix_billing_service.apply_invoice_paid(self.inv)
        first_end = StoreSubscription.objects.get(pk=self.sub.pk).current_period_end
        pix_billing_service.apply_invoice_paid(self.inv)
        self.assertEqual(StoreSubscription.objects.get(pk=self.sub.pk).current_period_end, first_end)

    def test_exempt_store_ignored(self):
        self.store.billing_exempt = True; self.store.save()
        res = pix_billing_service.apply_invoice_paid(self.inv)
        self.assertEqual(res.get("processed"), False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.ApplyInvoicePaidTest -v 2`
Expected: FAIL (`apply_invoice_paid` inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# apps/stores/services/pix_billing_service.py — acrescentar
def apply_invoice_paid(store_payment):
    """Fatura PIX paga → avança a assinatura. Idempotente."""
    meta = store_payment.metadata or {}
    sub_id = meta.get("subscription_id")
    if not sub_id:
        return {"processed": False, "reason": "no_subscription"}
    if meta.get("applied"):
        return {"processed": False, "reason": "already_applied"}
    sub = StoreSubscription.objects.select_related("store").filter(pk=sub_id).first()
    if not sub:
        return {"processed": False, "reason": "subscription_not_found"}
    store = sub.store
    if billing.is_billing_exempt(store):
        return {"processed": False, "reason": "billing_exempt"}

    now = timezone.now()
    base = sub.current_period_end if (sub.current_period_end and sub.current_period_end > now) else now
    months = 12 if meta.get("kind") == "annual" else 1
    # +N meses sem dependência extra: soma ~30d por mês é impreciso; usar relativedelta
    from dateutil.relativedelta import relativedelta
    sub.current_period_end = base + relativedelta(months=months)
    sub.status = StoreSubscription.Status.ACTIVE
    sub.dunning_since = None
    sub.grace_until = None
    sub.downgraded_for_nonpayment = False
    if not sub.started_at:
        sub.started_at = now
    sub.save(update_fields=[
        "current_period_end", "status", "dunning_since", "grace_until",
        "downgraded_for_nonpayment", "started_at",
    ])
    if store.plan != sub.plan:
        store.plan = sub.plan
        store.save(update_fields=["plan"])

    meta["applied"] = True
    store_payment.metadata = meta
    store_payment.save(update_fields=["metadata"])
    logger.info("Fatura %s paga → assinatura %s ACTIVE até %s", store_payment.id, sub.id, sub.current_period_end)
    return {"processed": True, "period_end": sub.current_period_end}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.ApplyInvoicePaidTest -v 2`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/pix_billing_service.py apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): apply_invoice_paid avanca assinatura no PIX pago"
```

---

### Task 4: Ligar reconciliação — fatura `subpix:` COMPLETED chama `apply_invoice_paid`

**Files:**
- Modify: `apps/stores/services/checkout_service.py` (`_handle_storepayment_webhook`, ~L1572-1633)
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Consumes: `pix_billing_service.apply_invoice_paid`.
- Produces: quando `_handle_storepayment_webhook` marca um StorePayment `COMPLETED` cujo `external_reference` começa com `subpix:`, chama `apply_invoice_paid(payment)`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py — nova classe
class WebhookAdvancesSubscriptionTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Loja Z", slug="loja-z", plan="free")
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro",
            status=StoreSubscription.Status.PAST_DUE)
        self.inv = StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_id="777", external_reference=f"subpix:{self.sub.id}:2026-07",
            metadata={"kind": "monthly", "subscription_id": self.sub.id},
        )

    def test_approved_webhook_activates_subscription(self):
        from apps.stores.services.checkout_service import CheckoutService
        CheckoutService().process_payment_webhook("777", "approved", external_reference=f"subpix:{self.sub.id}:2026-07")
        self.sub.refresh_from_db(); self.store.refresh_from_db()
        self.assertEqual(self.sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.store.plan, "pro")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.WebhookAdvancesSubscriptionTest -v 2`
Expected: FAIL (assinatura fica PAST_DUE — StorePayment vira COMPLETED mas nada avança a assinatura).

- [ ] **Step 3: Hook em `_handle_storepayment_webhook`**

No fim do bloco que marca `payment.status = COMPLETED` e salva (após `paid_at`), adicionar:

```python
# apps/stores/services/checkout_service.py — dentro de _handle_storepayment_webhook,
# depois de marcar COMPLETED/paid_at e salvar o StorePayment:
if (payment.external_reference or "").startswith("subpix:"):
    from apps.stores.services import pix_billing_service
    pix_billing_service.apply_invoice_paid(payment)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.WebhookAdvancesSubscriptionTest -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/stores/services/checkout_service.py apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): webhook de fatura subpix avanca a assinatura"
```

---

### Task 5: Lifecycle — inadimplência cai pro Grátis (não suspende) + marca razão

**Files:**
- Modify: `apps/stores/services/subscription_lifecycle.py` (`decide_transition`)
- Modify: `apps/stores/tasks.py` (`enforce_subscription_lifecycle` — aplicar `downgrade_free` marcando `downgraded_for_nonpayment=True`)
- Test: `apps/stores/tests/test_subscription_lifecycle.py` (arquivo existente)

**Interfaces:**
- Consumes: `Transition(action)` existente.
- Produces: `decide_transition` retorna `downgrade_free` (em vez de `suspend`) quando `past_due` + dunning esgotado. A task, ao aplicar `downgrade_free` por inadimplência, seta `sub.downgraded_for_nonpayment=True`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_subscription_lifecycle.py — novo teste
from datetime import datetime, timezone as dtz, timedelta
from apps.stores.services.subscription_lifecycle import decide_transition

def test_past_due_after_dunning_downgrades_not_suspends():
    now = datetime(2026, 7, 10, tzinfo=dtz.utc)
    t = decide_transition(
        status="past_due", trial_ends_at=None,
        grace_until=None, dunning_since=now - timedelta(days=5),
        now=now, grace_days=3, dunning_days=3, billing_exempt=False,
    )
    assert t.action == "downgrade_free"
```

(Se já existir um teste afirmando `suspend` nesse cenário, atualizá-lo para `downgrade_free` — é a mudança de comportamento intencional.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_subscription_lifecycle -v 2`
Expected: FAIL (hoje retorna `suspend`).

- [ ] **Step 3: Alterar a regra**

Em `decide_transition`, no ramo `past_due` com dunning esgotado, trocar `action="suspend"` por `action="downgrade_free"`.

- [ ] **Step 4: Aplicar razão na task**

```python
# apps/stores/tasks.py — no ramo elif t.action == 'downgrade_free':
elif t.action == 'downgrade_free':
    sub.status = StoreSubscription.Status.CANCELED
    was_paid_plan = store.plan != 'free'
    sub.downgraded_for_nonpayment = was_paid_plan  # veio de plano pago não pago
    sub.save(update_fields=['status', 'downgraded_for_nonpayment'])
    if was_paid_plan:
        store.plan = 'free'
        store.save(update_fields=['plan'])
    counts['downgraded_free'] += 1
```

- [ ] **Step 5: Run tests + commit**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_subscription_lifecycle apps.stores.tests.test_enforce_subscription_task -v 2`
Expected: PASS (ajustar testes de regressão que esperavam `suspend`).

```bash
git add apps/stores/services/subscription_lifecycle.py apps/stores/tasks.py apps/stores/tests/
git commit -m "feat(billing): inadimplencia cai pro Gratis (aviso) em vez de suspender"
```

---

### Task 6: Flag `BILLING_PIX_ENABLED` + geração automática de fatura na task

**Files:**
- Modify: `config/settings/base.py` (nova flag, junto das outras BILLING_*)
- Modify: `apps/stores/tasks.py` (`enforce_subscription_lifecycle`: gerar fatura ≤3 dias antes do fim do período/trial)
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Consumes: `pix_billing_service.generate_invoice`, `settings.BILLING_PIX_ENABLED`.
- Produces: a task, quando `BILLING_PIX_ENABLED` e a assinatura não-isenta está a ≤3 dias do `current_period_end` (ou `trial_ends_at`), chama `generate_invoice(sub)`.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py — nova classe
from django.test import override_settings

class AutoInvoiceGenerationTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="Loja W", slug="loja-w", plan="pro",
            trial_ends_at=timezone.now() + timezone.timedelta(days=2))
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro",
            status=StoreSubscription.Status.TRIALING)

    @override_settings(BILLING_PIX_ENABLED=True, BILLING_ENFORCEMENT_ENABLED=True)
    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_task_generates_invoice_near_trial_end(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        from apps.stores.tasks import enforce_subscription_lifecycle
        enforce_subscription_lifecycle()
        self.assertTrue(StorePayment.objects.filter(
            store=self.store, external_reference__startswith="subpix:").exists())

    @override_settings(BILLING_PIX_ENABLED=False, BILLING_ENFORCEMENT_ENABLED=True)
    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_flag_off_generates_nothing(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        from apps.stores.tasks import enforce_subscription_lifecycle
        enforce_subscription_lifecycle()
        self.assertFalse(StorePayment.objects.filter(
            store=self.store, external_reference__startswith="subpix:").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.AutoInvoiceGenerationTest -v 2`
Expected: FAIL.

- [ ] **Step 3: Add flag**

```python
# config/settings/base.py — junto das BILLING_*
BILLING_PIX_ENABLED = os.environ.get('BILLING_PIX_ENABLED', 'false').lower() == 'true'
```

- [ ] **Step 4: Gerar fatura na task**

```python
# apps/stores/tasks.py — dentro do loop, após decidir a transição, antes de fechar o for:
if getattr(settings, 'BILLING_PIX_ENABLED', False) and not store.billing_exempt:
    from apps.stores.services import pix_billing_service
    due = sub.current_period_end or store.trial_ends_at
    if due and (due - now).days <= 3 and sub.status in (
        StoreSubscription.Status.TRIALING, StoreSubscription.Status.ACTIVE,
        StoreSubscription.Status.PAST_DUE):
        try:
            pix_billing_service.generate_invoice(sub, now=now)
        except Exception:
            logger.exception('Falha ao gerar fatura PIX p/ %s', store.slug)
```

- [ ] **Step 5: Run tests + commit**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing -v 2`
Expected: PASS (toda a suíte da Fase 1).

```bash
git add config/settings/base.py apps/stores/tasks.py apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): flag BILLING_PIX_ENABLED + geracao automatica de fatura na varredura"
```

---

### Task 7: Catálogo expõe preço anual + endpoints de fatura no dash

**Files:**
- Modify: `apps/stores/billing.py` (helper `annual_price(plan_key)`)
- Modify: catálogo público (view de `/public/plans/`) para incluir `annual_price`
- Create: view `StoreInvoiceView` (`GET /stores/{slug}/invoices/`, `GET /stores/{slug}/invoices/current/`) em `apps/stores/api/views/subscription_views.py`
- Modify: `apps/stores/urls.py` (rotas)
- Modify: `apps/stores/api/payment_views.py` (`StorePaymentViewSet.get_queryset` → incluir `Q(store=...)`)
- Test: `apps/stores/tests/test_pix_billing.py`

**Interfaces:**
- Consumes: `pix_billing_service.generate_invoice`, `billing.PLAN_CATALOG`.
- Produces: `annual_price(plan_key) -> Decimal` (mensal×10); `/public/plans/` cada plano com `annual_price`; `GET /stores/{slug}/invoices/current/` retorna a fatura vigente (gera se dentro da janela e não existe) como `{id, amount, status, kind, pix_code, pix_qr_code, ticket_url, expires_at, period_key}`; `GET /stores/{slug}/invoices/` lista as faturas `subpix:` da loja.

- [ ] **Step 1: Write the failing test**

```python
# apps/stores/tests/test_pix_billing.py — nova classe
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

class InvoiceEndpointTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="dono", password="x")
        self.store = Store.objects.create(name="Loja E", slug="loja-e", plan="pro", owner=self.owner)
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_reference=f"subpix:{self.sub.id}:2026-07",
            qr_code="COPIACOLA", qr_code_base64="B64",
            metadata={"kind": "monthly", "subscription_id": self.sub.id},
        )
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def test_list_invoices_returns_subpix_charges(self):
        r = self.client.get(f"/api/v1/stores/{self.store.slug}/invoices/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["invoices"]), 1)
        self.assertEqual(r.data["invoices"][0]["pix_code"], "COPIACOLA")

    def test_public_plans_expose_annual_price(self):
        r = self.client.get("/api/v1/public/plans/")
        pro = next(p for p in r.data["plans"] if p["key"] == "pro")
        self.assertEqual(float(pro["annual_price"]), 2490.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.InvoiceEndpointTest -v 2`
Expected: FAIL (rota/annual_price inexistentes).

- [ ] **Step 3: Implementar helper, view, rotas, queryset**

```python
# apps/stores/billing.py
def annual_price(plan_key):
    from decimal import Decimal
    return Decimal(str(get_plan(plan_key)["monthly_price"])) * 10
```

```python
# apps/stores/api/views/subscription_views.py — nova view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.stores.models import Store, StorePayment, StoreSubscription
from apps.stores.permissions import IsStoreOwnerOrStaff  # padrão do projeto

def _invoice_dict(p):
    return {
        "id": str(p.payment_id), "amount": float(p.amount), "status": p.status,
        "kind": (p.metadata or {}).get("kind"), "pix_code": p.qr_code,
        "pix_qr_code": p.qr_code_base64, "ticket_url": p.ticket_url,
        "expires_at": p.expires_at, "period_key": (p.metadata or {}).get("period_key"),
        "paid_at": p.paid_at,
    }

class StoreInvoiceListView(APIView):
    permission_classes = [IsAuthenticated, IsStoreOwnerOrStaff]
    def get(self, request, store_slug):
        store = Store.objects.get(slug=store_slug)
        self.check_object_permissions(request, store)
        qs = StorePayment.objects.filter(
            store=store, external_reference__startswith="subpix:").order_by("-created_at")
        return Response({"invoices": [_invoice_dict(p) for p in qs]})

class StoreInvoiceCurrentView(APIView):
    permission_classes = [IsAuthenticated, IsStoreOwnerOrStaff]
    def get(self, request, store_slug):
        store = Store.objects.get(slug=store_slug)
        self.check_object_permissions(request, store)
        sub = StoreSubscription.objects.filter(store=store).first()
        if not sub:
            return Response({"invoice": None})
        from apps.stores.services import pix_billing_service
        inv = pix_billing_service.generate_invoice(sub)  # idempotente; None se isenta
        return Response({"invoice": _invoice_dict(inv) if inv else None})
```

```python
# apps/stores/urls.py — adicionar (padrão das rotas subscription/)
path('stores/<slug:store_slug>/invoices/', StoreInvoiceListView.as_view()),
path('stores/<slug:store_slug>/invoices/current/', StoreInvoiceCurrentView.as_view()),
```

```python
# apps/stores/api/payment_views.py — StorePaymentViewSet.get_queryset
# trocar filtro por: Q(order__store__in=accessible) | Q(store__in=accessible)
from django.db.models import Q
qs = StorePayment.objects.filter(Q(order__store__in=stores) | Q(store__in=stores))
```

E incluir `annual_price` no serializer/dict do `/public/plans/` (onde monta cada plano, adicionar `"annual_price": float(billing.annual_price(key))` para planos pagos).

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing.InvoiceEndpointTest -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/stores/billing.py apps/stores/api/ apps/stores/urls.py apps/stores/tests/test_pix_billing.py
git commit -m "feat(billing): endpoints de fatura PIX + preco anual no catalogo publico"
```

---

### Task 8: Suíte completa + smoke em loja de teste

**Files:**
- Test: toda a suíte de billing.

- [ ] **Step 1: Rodar a suíte de billing inteira**

Run: `docker compose exec -T web python manage.py test apps.stores.tests.test_pix_billing apps.stores.tests.test_subscription_lifecycle apps.stores.tests.test_enforce_subscription_task apps.stores.tests.test_billing apps.stores.tests.test_subscription -v 2`
Expected: tudo verde, zero regressão.

- [ ] **Step 2: Smoke manual (documentar, não automatizar)**

Com `BILLING_PIX_ENABLED=true` só em ambiente de teste: numa loja NÃO-isenta (`testezaco`), chamar `generate_invoice`, pagar o PIX com valor baixo (ex.: ajustar plano de teste), confirmar via webhook que a assinatura vira `ACTIVE` e `store.plan` aplica. Reverter.

- [ ] **Step 3: Commit (se houver ajuste)**

```bash
git commit -am "test(billing): suite de fase 1 verde + notas de smoke"
```

---

## Self-Review

**Spec coverage (Fase 1):**
- Modelo de dados (StorePayment etiquetado + billing_cycle) → Tasks 1, 2. ✅
- generate_invoice na conta da plataforma → Task 2. ✅
- apply_invoice_paid (avança assinatura) → Task 3. ✅
- Reconciliação webhook → Task 4. ✅
- Não-pagamento cai pro Grátis + razão → Task 5. ✅
- Flag + geração automática → Task 6. ✅
- Anual (preço) + endpoints + queryset avulso → Task 7. ✅
- Fora da Fase 1 (planos próprios): WhatsApp (seção 4 do spec) e tela de fatura no dash (seção 7). Documentado no topo.

**Placeholders:** nenhum passo sem código; comandos com expected output. ✅
**Type consistency:** `generate_invoice(subscription, now=None)`, `apply_invoice_paid(store_payment)`, `external_reference=subpix:{id}:{period_key}`, `metadata.kind/subscription_id/period_key/applied` — consistentes entre tasks. ✅

**Nota de verificação para o executor:** confirmar os nomes reais no código antes de cada task — `StorePayment.PaymentStatus.COMPLETED`/`PaymentMethod.PIX`, campos `qr_code`/`qr_code_base64`/`ticket_url`/`metadata`, assinatura de `process_payment_webhook(payment_id, status, external_reference=...)`, e o nome exato da permission class (`IsStoreOwnerOrStaff`) e do queryset de lojas acessíveis em `StorePaymentViewSet`. Ajustar se divergir.
