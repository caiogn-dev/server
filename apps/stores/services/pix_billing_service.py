"""Cobrança de assinatura SaaS via PIX (fatura mensal/anual).

A fatura é um StorePayment avulso (order=None) cobrado na conta da PLATAFORMA
(subscription_service._sdk()), não no gateway da loja. Reconciliação e ciclo
de vida reaproveitam a infra existente.
"""
import logging
from decimal import Decimal
from dateutil.relativedelta import relativedelta
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
            "kind": kind, "subscription_id": str(subscription.id),
            "period_key": period_key, "sent_steps": [],
        },
    )


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
