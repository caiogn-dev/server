from unittest.mock import patch, MagicMock
from datetime import datetime, timezone as dtz
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from apps.stores.models import Store, StoreSubscription, StorePayment
from apps.stores.services import pix_billing_service


class BillingCycleFieldTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix', 'owner_pix@x.com', 'x')
        self.store = Store.objects.create(name="Loja Teste", slug="loja-teste", owner=self.owner)

    def test_subscription_defaults_monthly_and_not_downgraded(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        self.assertEqual(sub.billing_cycle, "monthly")
        self.assertFalse(sub.downgraded_for_nonpayment)

    def test_billing_cycle_accepts_annual(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro", billing_cycle="annual")
        self.assertEqual(sub.billing_cycle, "annual")


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
        self.owner = User.objects.create_user('owner_pix_invoice', 'owner_pix_invoice@x.com', 'x')
        self.store = Store.objects.create(name="Loja X", slug="loja-x", plan="pro", owner=self.owner)
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
        self.assertEqual(float(inv.amount), 329.0)  # "Loja + WhatsApp" mensal
        self.assertEqual(inv.metadata["kind"], "monthly")

    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_annual_is_ten_times_monthly(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        self.sub.billing_cycle = "annual"; self.sub.save()
        inv = pix_billing_service.generate_invoice(self.sub, now=self.now)
        self.assertEqual(float(inv.amount), 3290.0)  # 329 x 10 (paga 10, leva 12)
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


class ApplyInvoicePaidTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix_apply', 'owner_pix_apply@x.com', 'x')
        self.store = Store.objects.create(name="Loja Y", slug="loja-y", plan="free", owner=self.owner)
        self.sub = StoreSubscription.objects.create(
            store=self.store, plan="pro", status=StoreSubscription.Status.PAST_DUE,
            dunning_since=timezone.now(), downgraded_for_nonpayment=True,
        )
        self.inv = StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.COMPLETED,
            external_reference=f"subpix:{self.sub.id}:2026-07",
            metadata={"kind": "monthly", "subscription_id": str(self.sub.id)},
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


class WebhookAdvancesSubscriptionTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix_webhook', 'owner_pix_webhook@x.com', 'x')
        self.store = Store.objects.create(name="Loja Z", slug="loja-z", plan="free", owner=self.owner)
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro",
            status=StoreSubscription.Status.PAST_DUE)
        self.inv = StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_id="777", external_reference=f"subpix:{self.sub.id}:2026-07",
            metadata={"kind": "monthly", "subscription_id": str(self.sub.id)},
        )

    def test_approved_webhook_activates_subscription(self):
        from apps.stores.services.checkout_service import CheckoutService
        CheckoutService().process_payment_webhook("777", "approved", external_reference=f"subpix:{self.sub.id}:2026-07")
        self.sub.refresh_from_db(); self.store.refresh_from_db()
        self.assertEqual(self.sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.store.plan, "pro")


class AutoInvoiceGenerationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix_auto', 'owner_pix_auto@x.com', 'x')
        self.store = Store.objects.create(
            name="Loja W", slug="loja-w", plan="pro", owner=self.owner,
            trial_ends_at=timezone.now() + timezone.timedelta(days=2),
        )
        self.sub = StoreSubscription.objects.create(
            store=self.store, plan="pro", status=StoreSubscription.Status.TRIALING,
        )

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

    @override_settings(BILLING_PIX_ENABLED=True, BILLING_ENFORCEMENT_ENABLED=True)
    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_exempt_store_never_invoiced_by_task(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        self.store.billing_exempt = True
        self.store.save(update_fields=["billing_exempt"])
        from apps.stores.tasks import enforce_subscription_lifecycle
        enforce_subscription_lifecycle()
        self.assertFalse(StorePayment.objects.filter(
            store=self.store, external_reference__startswith="subpix:").exists())

    @override_settings(BILLING_PIX_ENABLED=True, BILLING_ENFORCEMENT_ENABLED=True)
    @patch.object(pix_billing_service.subscription_service, "_sdk")
    def test_task_is_idempotent_across_runs(self, mock_sdk):
        mock_sdk.return_value = _fake_pix_sdk()
        from apps.stores.tasks import enforce_subscription_lifecycle
        enforce_subscription_lifecycle()
        enforce_subscription_lifecycle()
        self.assertEqual(
            StorePayment.objects.filter(
                store=self.store, external_reference__startswith="subpix:").count(),
            1,
        )


class InvoiceEndpointTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix_invoice_ep', 'owner_pix_invoice_ep@x.com', 'x')
        self.store = Store.objects.create(name="Loja E", slug="loja-e", plan="pro", owner=self.owner)
        self.sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        self.period_key = pix_billing_service._period_key(self.sub, timezone.now())
        self.invoice = StorePayment.objects.create(
            store=self.store, order=None, amount=249, currency="BRL",
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_reference=f"subpix:{self.sub.id}:{self.period_key}",
            qr_code="COPIACOLA", qr_code_base64="B64",
            metadata={"kind": "monthly", "subscription_id": str(self.sub.id), "period_key": self.period_key},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_list_invoices_returns_subpix_charges(self):
        r = self.client.get(f"/api/v1/stores/{self.store.slug}/invoices/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["invoices"]), 1)
        self.assertEqual(r.data["invoices"][0]["pix_code"], "COPIACOLA")

    def test_current_invoice_returns_existing_period_invoice(self):
        r = self.client.get(f"/api/v1/stores/{self.store.slug}/invoices/current/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["invoice"])
        self.assertEqual(r.data["invoice"]["pix_code"], "COPIACOLA")
        self.assertEqual(r.data["invoice"]["period_key"], self.period_key)

    def test_current_invoice_none_when_billing_exempt(self):
        self.store.billing_exempt = True
        self.store.save(update_fields=["billing_exempt"])
        r = self.client.get(f"/api/v1/stores/{self.store.slug}/invoices/current/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["invoice"])

    def test_invoice_endpoints_require_permission(self):
        other = User.objects.create_user('outsider_invoice', 'outsider_invoice@x.com', 'x')
        client = APIClient()
        client.force_authenticate(other)
        r = client.get(f"/api/v1/stores/{self.store.slug}/invoices/")
        self.assertEqual(r.status_code, 403)

    def test_public_plans_expose_annual_price(self):
        r = self.client.get("/api/v1/public/plans/")
        pro = next(p for p in r.data["plans"] if p["key"] == "pro")
        self.assertEqual(float(pro["annual_price"]), 3290.0)  # 329 x 10
        free = next(p for p in r.data["plans"] if p["key"] == "free")
        self.assertNotIn("annual_price", free)

    def test_payment_viewset_lists_avulso_store_payments(self):
        r = self.client.get(f"/api/v1/stores/payments/?store={self.store.id}")
        self.assertEqual(r.status_code, 200)
        ids = [p["id"] for p in r.data] if isinstance(r.data, list) else [p["id"] for p in r.data.get("results", [])]
        self.assertIn(str(self.invoice.id), ids)
