# O checkout nao pode recusar 'voucher' antes de chegar na cobranca.
from apps.stores.api.serializers import CheckoutSerializer


def _campo():
    return CheckoutSerializer().fields['payment_method']


def test_voucher_e_um_metodo_aceito_no_checkout():
    assert 'voucher' in _campo().choices


def test_os_metodos_que_ja_existiam_continuam_aceitos():
    for metodo in ('pix', 'card', 'cash'):
        assert metodo in _campo().choices


def test_o_default_continua_pix():
    assert _campo().default == 'pix'
