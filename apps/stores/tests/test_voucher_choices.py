import pytest
from apps.stores.models import StorePayment, StorePaymentGateway


def test_pagarme_e_um_tipo_de_gateway():
    assert StorePaymentGateway.GatewayType.PAGARME == 'pagarme'


def test_voucher_e_um_metodo_de_pagamento():
    assert StorePayment.PaymentMethod.VOUCHER == 'voucher'


def test_os_valores_cabem_nas_colunas():
    """max_length=20 nas duas colunas. Um valor maior truncaria em silêncio."""
    assert len(StorePaymentGateway.GatewayType.PAGARME.value) <= 20
    assert len(StorePayment.PaymentMethod.VOUCHER.value) <= 20
