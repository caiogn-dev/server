"""Qual provider atende qual gateway.

Quando a Volus chegar, ela é uma classe nova e UMA linha em `_PROVIDERS`.
Checkout, modelo e máquina de estados não mudam.
"""
from apps.stores.models import StorePaymentGateway

from .base import VoucherProvider
from .pagarme import PagarmeVoucherProvider

_PROVIDERS = {
    StorePaymentGateway.GatewayType.PAGARME.value: PagarmeVoucherProvider,
}

#: Gateways capazes de cobrar voucher, na ordem de preferência.
GATEWAYS_DE_VOUCHER = tuple(_PROVIDERS)


def provider_para(gateway) -> VoucherProvider:
    classe = _PROVIDERS.get(getattr(gateway, 'gateway_type', ''))
    if classe is None:
        raise ValueError(
            f'Nenhum provider de voucher para o gateway {gateway.gateway_type!r}.'
        )
    return classe(gateway)


def gateway_de_voucher(store):
    """O gateway de voucher habilitado da loja, ou None."""
    return (
        StorePaymentGateway.objects
        .filter(store=store, gateway_type__in=GATEWAYS_DE_VOUCHER, is_enabled=True)
        .order_by('-is_default', 'name')
        .first()
    )


def bandeiras_manuais_da_loja(store):
    """Bandeiras SEM integração que a loja aceita, cobradas por link.

    Não exige gateway: o dinheiro não passa por API nenhuma. A loja marca a
    bandeira, o cliente escolhe, o pedido nasce pendente e a cobrança vai por
    WhatsApp. Por isso a config mora no Store, não no gateway.
    """
    from apps.stores.services.voucher import bandeiras
    config = (store.metadata or {}) if isinstance(store.metadata, dict) else {}
    marcadas = config.get('voucher_manual_brands') or []
    validas = set(bandeiras.valores_manuais())
    return [str(m).strip().lower() for m in marcadas
            if str(m).strip().lower() in validas]


def bandeiras_da_loja(store):
    """Bandeiras que a loja aceita. Lista vazia quando não aceita voucher."""
    gateway = gateway_de_voucher(store)
    if not gateway or not gateway.public_key or not gateway.api_key:
        return []
    return provider_para(gateway).bandeiras()
