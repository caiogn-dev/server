"""Silenciar o pedido também vale no caminho de reserva.

`StoreOrder._trigger_status_whatsapp_notification` é o segundo motor de aviso
de status: entra quando a tarefa do WhatsApp não cobre o caso. Ele NUNCA olhou
`suppress_notifications` — a loja silenciava a venda de balcão e o cliente
recebia assim mesmo, por esta porta.
"""
from unittest import mock

import pytest

from apps.stores.tests.factories import make_store


def _pedido(loja, **extra):
    from apps.stores.models.order import StoreOrder

    return StoreOrder.objects.create(
        store=loja, customer_name='Ana', customer_phone='5563911119999',
        total=Decimal('10.00'), subtotal=Decimal('10.00'), **extra,
    )


from decimal import Decimal  # noqa: E402


@pytest.mark.django_db
def test_pedido_silenciado_nao_avisa_pelo_caminho_de_reserva():
    loja = make_store()
    pedido = _pedido(loja, metadata={'suppress_notifications': True})

    with mock.patch('apps.automation.mensageiro.enviar_texto') as envio:
        pedido._trigger_status_whatsapp_notification('preparing')

    envio.assert_not_called()


@pytest.mark.django_db
def test_pedido_normal_continua_avisando():
    loja = make_store()
    pedido = _pedido(loja)

    with mock.patch.object(type(loja), 'get_whatsapp_account', return_value=_Conta()), \
            mock.patch('apps.automation.mensageiro.enviar_texto') as envio:
        pedido._trigger_status_whatsapp_notification('preparing')

    envio.assert_called_once()
    assert envio.call_args.kwargs['evento'] == 'order_preparing'


class _Conta:
    id = 'conta-fake'
    phone_number_id = 'PH-FAKE'
