"""
Catálogo de planos e helpers de feature-gate do SaaS Cardapidex.

Valores/limites são PLACEHOLDER configuráveis (definidos aqui, fonte única).
Enforcement (bloquear ações por plano) e cobrança MercadoPago são wired no
sub-projeto Billing — este módulo só define o catálogo e os helpers de leitura.
"""
from decimal import Decimal

# Catálogo dos 3 planos. limits.max_products=None => ilimitado.
PLAN_CATALOG = {
    'starter': {
        'key': 'starter',
        'name': 'Starter',
        'setup_fee': Decimal('99.00'),
        'monthly_price': Decimal('59.00'),
        'limits': {
            'max_products': 50,
            'custom_domain': False,
            'whatsapp_bot': False,
            'ai_agent': False,
        },
    },
    'pro': {
        'key': 'pro',
        'name': 'Pro',
        'setup_fee': Decimal('149.00'),
        'monthly_price': Decimal('99.00'),
        'limits': {
            'max_products': None,
            'custom_domain': True,
            'whatsapp_bot': True,
            'ai_agent': False,
        },
    },
    'premium': {
        'key': 'premium',
        'name': 'Premium',
        'setup_fee': Decimal('199.00'),
        'monthly_price': Decimal('159.00'),
        'limits': {
            'max_products': None,
            'custom_domain': True,
            'whatsapp_bot': True,
            'ai_agent': True,
        },
    },
}

DEFAULT_PLAN = 'starter'


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
    True se o plano da loja permite a feature.
    NÃO é enforcement automático — chamadores decidem quando aplicar.
    Features booleanas: custom_domain, whatsapp_bot, ai_agent.
    """
    if is_billing_exempt(store):
        return True
    limits = plan_limits(getattr(store, 'plan', DEFAULT_PLAN))
    return bool(limits.get(feature, False))


def within_product_limit(store, current_count):
    """True se a loja ainda pode adicionar produto (None = ilimitado)."""
    if is_billing_exempt(store):
        return True
    cap = plan_limits(getattr(store, 'plan', DEFAULT_PLAN)).get('max_products')
    return cap is None or current_count < cap


def public_catalog():
    """Catálogo serializável (para landing/dash). Decimals viram float/str."""
    out = []
    for p in PLAN_CATALOG.values():
        out.append({
            'key': p['key'],
            'name': p['name'],
            'setup_fee': float(p['setup_fee']),
            'monthly_price': float(p['monthly_price']),
            'limits': p['limits'],
        })
    return out
