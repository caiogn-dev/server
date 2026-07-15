"""
Catálogo de planos e helpers de feature-gate do SaaS Cardapidex.

Valores/limites são PLACEHOLDER configuráveis (definidos aqui, fonte única).
Enforcement (bloquear ações por plano) e cobrança MercadoPago são wired no
sub-projeto Billing — este módulo só define o catálogo e os helpers de leitura.
"""
from decimal import Decimal

from django.utils import timezone

# Catálogo dos 4 planos. limits.max_products / max_orders_per_month = None => ilimitado.
PLAN_CATALOG = {
    'free': {
        'key': 'free',
        'name': 'Grátis',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('0.00'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': 40,
            'max_orders_per_month': 30,
            'custom_domain': False,
            'whatsapp_bot': False,
            'ai_agent': False,
        },
    },
    'starter': {
        'key': 'starter',
        'name': 'Essencial',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('99.90'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': False,
            'whatsapp_bot': False,
            'ai_agent': False,
        },
    },
    'pro': {
        'key': 'pro',
        'name': 'Pro',
        'setup_fee': Decimal('0.00'),
        'monthly_price': Decimal('249.00'),
        'charges_setup_fee': False,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': False,
            'whatsapp_bot': True,
            'ai_agent': False,
        },
    },
    'premium': {
        'key': 'premium',
        'name': 'Premium',
        'setup_fee': Decimal('149.00'),
        'monthly_price': Decimal('349.00'),
        'charges_setup_fee': True,
        'limits': {
            'max_products': None,
            'max_orders_per_month': None,
            'custom_domain': True,
            'whatsapp_bot': True,
            'ai_agent': True,
        },
    },
}

DEFAULT_PLAN = 'free'


def get_plan(plan_key):
    """Retorna a config do plano (fallback no default)."""
    return PLAN_CATALOG.get(plan_key) or PLAN_CATALOG[DEFAULT_PLAN]


def plan_limits(plan_key):
    return get_plan(plan_key)['limits']


def is_billing_exempt(store):
    """Lojas grandfather (pré-SaaS) não têm limites nem cobrança."""
    return bool(getattr(store, 'billing_exempt', False))


def plan_allows(store, feature):
    """
    True se o plano permite a feature.
    Aceita uma instância de Store OU diretamente uma plan_key (str).
    NÃO é enforcement automático — chamadores decidem quando aplicar.
    Features booleanas: custom_domain, whatsapp_bot, ai_agent.
    """
    if isinstance(store, str):
        return bool(plan_limits(store).get(feature, False))
    if is_billing_exempt(store):
        return True
    limits = plan_limits(getattr(store, 'plan', DEFAULT_PLAN))
    return bool(limits.get(feature, False))


def bot_order_allowed(store):
    """True se a loja pode usar o BOT DE PEDIDOS do WhatsApp (feature Pro/Premium).

    Isentas passam sempre; trial ativo libera tudo (o lojista precisa provar o
    produto); fora isso decide o plano (limits.whatsapp_bot).
    """
    if is_billing_exempt(store):
        return True
    trial_ends = getattr(store, 'trial_ends_at', None)
    if trial_ends and trial_ends > timezone.now():
        return True
    return plan_allows(store, 'whatsapp_bot')


def within_product_limit(store, current_count):
    """True se a loja ainda pode adicionar produto (None = ilimitado)."""
    if is_billing_exempt(store):
        return True
    cap = plan_limits(getattr(store, 'plan', DEFAULT_PLAN)).get('max_products')
    return cap is None or current_count < cap


def orders_in_current_month(store) -> int:
    """Conta pedidos da loja no mês corrente (fuso local).

    Usa um range [início_do_mês, início_do_próximo_mês) em vez de
    created_at__year/__month — o `__month` gera EXTRACT(MONTH ...) que impede o
    índice (store, created_at) de restringir ao mês (só restringia ao ano). O
    range é montado em horário LOCAL (timezone.localtime) para casar com a
    semântica de "mês" que o cliente enxerga, e comparado contra created_at
    (UTC no banco); o Django converte os limites aware para UTC.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.stores.models import StoreOrder
    now_local = timezone.localtime(timezone.now())
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    return StoreOrder.objects.filter(
        store=store,
        created_at__gte=month_start,
        created_at__lt=next_month,
    ).count()


def within_order_limit(store, current_month_count):
    """True se a loja ainda pode receber pedido neste mês (None = ilimitado)."""
    if is_billing_exempt(store):
        return True
    cap = plan_limits(getattr(store, 'plan', DEFAULT_PLAN)).get('max_orders_per_month')
    return cap is None or current_month_count < cap


def store_accepts_orders(store):
    """False só se a assinatura está 'suspended' e a loja NÃO é isenta."""
    if is_billing_exempt(store):
        return True
    sub = getattr(store, 'subscription', None)
    return not (sub is not None and sub.status == 'suspended')


def charges_setup_fee(plan_key):
    """True se ESTE plano deve cobrar a taxa de adesão (setup_fee). Toggle por plano."""
    return bool(get_plan(plan_key).get('charges_setup_fee', False))


def annual_price(plan_key):
    """Preço anual do plano (mensal × 10 — paga 10, leva 12). Decimal."""
    return Decimal(str(get_plan(plan_key)['monthly_price'])) * 10


def public_catalog():
    """Catálogo serializável (para landing/dash). Decimals viram float/str."""
    out = []
    for p in PLAN_CATALOG.values():
        entry = {
            'key': p['key'],
            'name': p['name'],
            'setup_fee': float(p['setup_fee']),
            'monthly_price': float(p['monthly_price']),
            'limits': p['limits'],
        }
        if p['monthly_price'] > 0:
            entry['annual_price'] = float(annual_price(p['key']))
        out.append(entry)
    return out
