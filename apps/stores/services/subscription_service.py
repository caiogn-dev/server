"""
Assinatura SaaS via MercadoPago (preapproval recorrente).

O merchant é a PLATAFORMA Cardapidex (settings.MERCADO_PAGO_ACCESS_TOKEN),
não o gateway da loja. Criar a assinatura gera um init_point que o DONO
autoriza com o cartão dele — não cobra ninguém automaticamente.

A cobrança automática no fim do trial é gated por settings.BILLING_AUTOCHARGE_ENABLED
(default False) — fica pronta mas desligada até validar em sandbox.
"""
import logging
from django.conf import settings
from django.utils import timezone
from apps.stores import billing
from apps.stores.models import StoreSubscription

logger = logging.getLogger(__name__)


class SubscriptionError(Exception):
    pass


def _sdk():
    token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
    if not token:
        raise SubscriptionError('MERCADO_PAGO_ACCESS_TOKEN não configurado.')
    import mercadopago
    return mercadopago.SDK(token)


def create_subscription(store, plan_key, payer_email, back_url):
    """
    Cria um preapproval (assinatura mensal) no MercadoPago para a loja.
    Retorna dict { 'init_point', 'preapproval_id' }. Persiste StoreSubscription.

    NÃO cobra: o dono precisa abrir o init_point e autorizar o cartão.
    A adesão (setup_fee) é cobrada à parte (1ª fatura/preference) — TODO no wiring final.
    """
    if billing.is_billing_exempt(store):
        raise SubscriptionError('Loja isenta de cobrança (grandfather).')

    plan = billing.get_plan(plan_key)
    sdk = _sdk()

    # URL pra onde o MercadoPago manda os eventos da assinatura (preapproval).
    backend = getattr(settings, 'BACKEND_URL', '').rstrip('/')
    notification_url = f"{backend}/webhooks/payments/mercadopago/" if backend else None

    data = {
        'reason': f"Cardapidex {plan['name']} — {store.name}",
        'auto_recurring': {
            'frequency': 1,
            'frequency_type': 'months',
            'transaction_amount': float(plan['monthly_price']),
            'currency_id': 'BRL',
        },
        'back_url': back_url,
        'payer_email': payer_email,
        'status': 'pending',
    }
    if notification_url:
        data['notification_url'] = notification_url

    resp = sdk.preapproval().create(data)
    if resp.get('status') not in (200, 201):
        logger.error('MP preapproval falhou: %s', resp)
        raise SubscriptionError(f"MercadoPago recusou a assinatura: {resp.get('status')}")

    body = resp['response']
    preapproval_id = body.get('id', '')
    init_point = body.get('init_point') or body.get('sandbox_init_point', '')

    sub, _ = StoreSubscription.objects.update_or_create(
        store=store,
        defaults={
            'plan': plan_key,
            'status': StoreSubscription.Status.TRIALING,
            'mp_preapproval_id': preapproval_id,
        },
    )
    # Reflete o plano escolhido na loja (limites passam a valer ao ativar a assinatura)
    store.plan = plan_key
    store.save(update_fields=['plan'])

    logger.info('Preapproval criado p/ loja %s plano %s: %s', store.slug, plan_key, preapproval_id)
    return {'init_point': init_point, 'preapproval_id': preapproval_id}


def apply_preapproval_event(preapproval_id, mp_status):
    """
    Atualiza StoreSubscription a partir de um evento de preapproval do webhook.
    mp_status: 'authorized' | 'paused' | 'cancelled' (MercadoPago).
    """
    sub = StoreSubscription.objects.filter(mp_preapproval_id=preapproval_id).select_related('store').first()
    if not sub:
        return {'processed': False, 'reason': 'subscription_not_found'}

    mapping = {
        'authorized': StoreSubscription.Status.ACTIVE,
        'paused': StoreSubscription.Status.PAST_DUE,
        'cancelled': StoreSubscription.Status.CANCELED,
    }
    new_status = mapping.get(mp_status)
    if not new_status:
        return {'processed': False, 'reason': f'unknown_status:{mp_status}'}

    sub.status = new_status
    if new_status == StoreSubscription.Status.ACTIVE and not sub.started_at:
        sub.started_at = timezone.now()
        sub.setup_fee_paid = True
    if new_status == StoreSubscription.Status.CANCELED:
        sub.canceled_at = timezone.now()
    sub.save()
    logger.info('Subscription %s → %s (loja %s)', preapproval_id, new_status, sub.store.slug)
    return {'processed': True, 'status': new_status}
