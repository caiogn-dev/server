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


def is_sandbox():
    return bool(getattr(settings, 'MERCADO_PAGO_SANDBOX_TOKEN', ''))


def _sdk():
    # Prefere o token de SANDBOX (TEST-) se setado — testa sem cobrar de verdade.
    token = getattr(settings, 'MERCADO_PAGO_SANDBOX_TOKEN', '') or getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
    if not token:
        raise SubscriptionError('Token MercadoPago não configurado.')
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
    # NÃO aplica o plano na loja aqui: o dono ainda precisa abrir o init_point e
    # pagar. O plano escolhido fica só na assinatura; store.plan (que governa os
    # feature-gates) só muda quando o preapproval for autorizado (apply_preapproval_event).

    result = {'init_point': init_point, 'preapproval_id': preapproval_id}

    # Taxa de adesão: preference one-off, gated por killswitch global + toggle do plano.
    setup_enabled = getattr(settings, 'BILLING_SETUP_FEE_ENABLED', False)
    setup_fee = plan.get('setup_fee')
    if setup_enabled and billing.charges_setup_fee(plan_key) and setup_fee is not None:
        pref_data = {
            'items': [{
                'title': f"Adesão Cardapidex {plan['name']} — {store.name}",
                'quantity': 1,
                'unit_price': float(setup_fee),
                'currency_id': 'BRL',
            }],
            'back_urls': {'success': back_url, 'pending': back_url, 'failure': back_url},
            'external_reference': f"setup:{store.slug}",
        }
        # Sem notification_url, o evento do pagamento da adesão dependeria só do
        # webhook global no painel MP. Com ele, o mesmo endpoint da assinatura
        # recebe o evento e a Task 7 desvia por external_reference 'setup:'.
        if notification_url:
            pref_data['notification_url'] = notification_url
        pref = sdk.preference().create(pref_data)
        if pref.get('status') in (200, 201):
            pref_body = pref['response']
            sub.mp_setup_payment_id = pref_body.get('id', '')
            sub.save(update_fields=['mp_setup_payment_id'])
            result['setup_init_point'] = pref_body.get('init_point') or pref_body.get('sandbox_init_point', '')
        else:
            logger.error('MP setup-fee preference falhou p/ loja %s: %s', store.slug, pref)

    logger.info('Preapproval criado p/ loja %s plano %s: %s', store.slug, plan_key, preapproval_id)
    return result


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
    store = sub.store
    if new_status == StoreSubscription.Status.ACTIVE:
        if not sub.started_at:
            sub.started_at = timezone.now()
            sub.setup_fee_paid = True
        # Pagamento autorizado: AGORA o plano pago vale na loja (feature-gates).
        if store.plan != sub.plan:
            store.plan = sub.plan
            store.save(update_fields=['plan'])
    if new_status == StoreSubscription.Status.CANCELED:
        sub.canceled_at = timezone.now()
        # Assinatura cancelada: loja perde o plano pago e volta pro default.
        if store.plan != billing.DEFAULT_PLAN:
            store.plan = billing.DEFAULT_PLAN
            store.save(update_fields=['plan'])
    sub.save()
    logger.info('Subscription %s → %s (loja %s)', preapproval_id, new_status, store.slug)
    return {'processed': True, 'status': new_status}


def cancel_subscription(store):
    """Cancela o preapproval no MP e marca a assinatura como canceled."""
    sub = StoreSubscription.objects.filter(store=store).first()
    if not sub:
        raise SubscriptionError('Loja sem assinatura.')
    if sub.mp_preapproval_id:
        try:
            _sdk().preapproval().update(sub.mp_preapproval_id, {'status': 'cancelled'})
        except Exception as e:
            logger.error('Falha ao cancelar preapproval %s: %s', sub.mp_preapproval_id, e)
    sub.status = StoreSubscription.Status.CANCELED
    sub.canceled_at = timezone.now()
    sub.save(update_fields=['status', 'canceled_at'])
    if store.plan != billing.DEFAULT_PLAN:
        store.plan = billing.DEFAULT_PLAN
        store.save(update_fields=['plan'])
    return sub


def change_plan(store, new_plan, payer_email, back_url):
    """Troca de plano = cancela o preapproval atual e cria um novo do plano alvo."""
    if new_plan not in ('starter', 'pro', 'premium'):
        raise SubscriptionError('Plano inválido.')
    existing = StoreSubscription.objects.filter(store=store).first()
    if existing and existing.mp_preapproval_id:
        try:
            _sdk().preapproval().update(existing.mp_preapproval_id, {'status': 'cancelled'})
        except Exception as e:
            logger.error('Falha ao cancelar preapproval antigo: %s', e)
    return create_subscription(store, new_plan, payer_email, back_url)


def mark_setup_fee_paid(external_reference, mp_status):
    """Marca setup_fee_paid=True quando o pagamento da adesão é aprovado.
    external_reference no formato 'setup:<store_slug>'."""
    if not (external_reference or '').startswith('setup:'):
        return {'processed': False, 'reason': 'not_setup_ref'}
    if mp_status != 'approved':
        return {'processed': False, 'reason': 'not_approved'}
    slug = external_reference.split(':', 1)[1]
    sub = StoreSubscription.objects.filter(store__slug=slug).first()
    if not sub:
        return {'processed': False, 'reason': 'subscription_not_found'}
    if not sub.setup_fee_paid:
        sub.setup_fee_paid = True
        sub.save(update_fields=['setup_fee_paid'])
        logger.info('Setup fee paga p/ loja %s', slug)
    return {'processed': True, 'slug': slug}
