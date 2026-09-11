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


def bandeiras_da_loja(store):
    """Bandeiras que a loja aceita. Lista vazia quando não aceita voucher."""
    gateway = gateway_de_voucher(store)
    if not gateway or not gateway.public_key or not gateway.api_key:
        return []
    return provider_para(gateway).bandeiras()
