import pytest

from apps.stores.services import pagarme_orders


def test_chamada_real_ao_pagarme_estoura_no_teste():
    with pytest.raises(AssertionError, match='DE VERDADE'):
        pagarme_orders.create_order('sk_test_x', {'items': []})


def test_consulta_real_ao_pagarme_tambem_estoura():
    with pytest.raises(AssertionError, match='DE VERDADE'):
        pagarme_orders.consultar_order('sk_test_x', 'or_1')
