"""Qual provider atende qual gateway.

Quando a Volus chegar, ela é uma classe nova e UMA linha em `_PROVIDERS`.
Checkout, modelo e máquina de estados não mudam.
"""
from apps.stores.models import StorePaymentGateway

from .base import VoucherProvider
from .cielo import CieloVoucherProvider
from .pagarme import PagarmeVoucherProvider

_PROVIDERS = {
    StorePaymentGateway.GatewayType.PAGARME.value: PagarmeVoucherProvider,
    StorePaymentGateway.GatewayType.CIELO.value: CieloVoucherProvider,
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


def _com_credencial(gateway) -> bool:
    return bool(gateway.public_key and gateway.api_key)


def gateways_de_voucher(store):
    """Todos os gateways de voucher habilitados da loja, o padrão primeiro.

    Uma loja pode ter dois: Pagar.me (VR, Pluxee, Ticket) e Cielo (Alelo).
    """
    return list(
        StorePaymentGateway.objects
        .filter(store=store, gateway_type__in=GATEWAYS_DE_VOUCHER, is_enabled=True)
        .order_by('-is_default', 'name')
    )


def gateway_de_voucher(store, bandeira=None):
    """O gateway que cobra `bandeira` nesta loja, ou None.

    Sem `bandeira`, o primeiro habilitado — o comportamento de quando só havia
    um trilho.
    """
    candidatos = gateways_de_voucher(store)
    if bandeira is None:
        return candidatos[0] if candidatos else None
    bandeira = str(bandeira).strip().lower()
    for gateway in candidatos:
        if _com_credencial(gateway) and bandeira in provider_para(gateway).bandeiras():
            return gateway
    return None


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


def bandeiras_por_gateway(store):
    """[(gateway, [bandeiras])] — só gateways com credencial e ao menos uma marca."""
    pares = []
    for gateway in gateways_de_voucher(store):
        if not _com_credencial(gateway):
            continue
        marcas = provider_para(gateway).bandeiras()
        if marcas:
            pares.append((gateway, marcas))
    return pares


def bandeiras_da_loja(store):
    """Bandeiras que a loja aceita, de todos os trilhos. Vazia = não aceita voucher."""
    vistas = []
    for _gateway, marcas in bandeiras_por_gateway(store):
        vistas.extend(m for m in marcas if m not in vistas)
    return vistas
