from unittest.mock import patch, MagicMock
from datetime import datetime, timezone as dtz
from django.test import TestCase
from django.contrib.auth.models import User
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
