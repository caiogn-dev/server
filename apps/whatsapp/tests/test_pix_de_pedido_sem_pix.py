"""Fernanda pediu o PIX 4 vezes e ouviu "Não encontrei pagamentos pendentes".

10/nov/2026, CE-2611099564: pedido do site com pagamento na entrega
(`card_on_delivery`), `payment_status='pending'`, em preparo. A cliente
resolveu pagar no PIX antes de chegar: "O código pix", "O código pix pra
pagar agr", "O código pix desse pedido". O handler só achava pedido pendente
COM pix_code já gerado (ou gerando há <2 min); este não tinha, e caía em
"Não encontrei pagamentos pendentes. Quer fazer um pedido novo?" — quatro
vezes, para quem tinha um pedido aberto e queria pagar.

Contrato: pedido pendente sem PIX → gera o PIX dele e manda o código.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store
from apps.whatsapp.intents.handlers.payment import PaymentStatusHandler

TELEFONE = '5563981421758'
CODIGO = '00020126580014br.gov.bcb.pix0136fernanda'


def _handler(store):
    h = PaymentStatusHandler.__new__(PaymentStatusHandler)
    h.account = MagicMock()
    h.conversation = MagicMock(phone_number=TELEFONE)
    h.company_profile = MagicMock()
    h.store = store
    h._whatsapp_service = MagicMock()
    h._get_session_manager = MagicMock(
        return_value=MagicMock(is_payment_pending=MagicMock(return_value=False)),
    )
    return h


def _pedido(store, **extra):
    from django.utils import timezone
    from datetime import timedelta
    pedido = StoreOrder.objects.create(
        store=store, customer_name='Fernanda', customer_email='f@t.com',
        customer_phone=TELEFONE, subtotal=Decimal('46.08'), total=Decimal('46.08'),
        payment_method='card_on_delivery', **extra,
    )
    StoreOrder.objects.filter(pk=pedido.pk).update(created_at=timezone.now() - timedelta(hours=16))
    pedido.refresh_from_db()
    return pedido


@pytest.mark.django_db
class TestPixDePedidoSemPix:
    def test_pedido_pendente_sem_pix_gera_o_pix_e_manda_o_codigo(self):
        store = make_store()
        pedido = _pedido(store)
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
            return_value={'success': True, 'pix_code': CODIGO},
        ) as cria:
            r = _handler(store).handle({'original_message': 'O código pix pra pagar agr'})

        assert cria.call_args.args[0] == pedido
        assert cria.call_args.kwargs.get('payment_method', 'pix') == 'pix'
        assert CODIGO in r.response_text
        assert 'Não encontrei' not in r.response_text

    def test_falha_ao_gerar_nao_diz_que_nao_ha_pedido(self):
        store = make_store()
        pedido = _pedido(store)
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
            return_value={'success': False, 'error': 'gateway fora'},
        ):
            r = _handler(store).handle({'original_message': 'pix'})

        assert 'Não encontrei' not in r.response_text
        assert pedido.order_number in r.response_text

    def test_sem_pedido_nenhum_continua_igual(self):
        store = make_store()
        r = _handler(store).handle({'original_message': 'pix'})
        assert 'Não encontrei pagamentos pendentes' in r.response_text

    def test_pedido_cancelado_nao_gera_pix(self):
        store = make_store()
        _pedido(store, status=StoreOrder.OrderStatus.CANCELLED)
        with patch(
            'apps.stores.services.checkout_service.CheckoutService.create_payment',
        ) as cria:
            _handler(store).handle({'original_message': 'pix'})
        cria.assert_not_called()
