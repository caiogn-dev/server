"""27/10, Odaíse (CE-2610275997): pagou o PIX às 12:24, o pedido saiu para
entrega, e às 13:17 perguntou "Vai demorar muito?". O agente chamou
`consultar_pagamento` e reenviou o código PIX como se o pagamento estivesse
pendente; ela respondeu "Já paguei."

Causa: `_get_pending_pix_payment` devolvia o `pix_code` da sessão/pedido sem
olhar `payment_status`. O código continua gravado no pedido depois de pago.
"""
from decimal import Decimal

import pytest

from apps.agents.services.langchain_service import LangchainService
from apps.automation.models import CompanyProfile, CustomerSession
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store

TELEFONE = '5563985155899'
CODIGO = '00020126360014br.gov.bcb.pix0114555997000001'


def _servico():
    return LangchainService.__new__(LangchainService)


def _pedido(store, payment_status, numero='CE-2610275997'):
    return StoreOrder.objects.create(
        store=store, order_number=numero, customer_name='Odaíse',
        customer_phone=TELEFONE, subtotal=Decimal('48.99'),
        delivery_fee=Decimal('12.34'), total=Decimal('61.33'),
        delivery_method='delivery', payment_method='pix',
        payment_status=payment_status, pix_code=CODIGO,
    )


def _sessao(store, pedido, status):
    profile, _ = CompanyProfile.objects.get_or_create(store=store)
    return CustomerSession.objects.create(
        company=profile, session_id='s-odaise', phone_number=TELEFONE,
        status=status, order=pedido, pix_code=CODIGO,
    )


@pytest.mark.django_db
class TestPixDePedidoJaPago:
    def test_pedido_pago_nao_devolve_o_pix(self):
        store = make_store()
        pedido = _pedido(store, StoreOrder.PaymentStatus.PAID)
        _sessao(store, pedido, 'payment_confirmed')

        r = _servico()._get_pending_pix_payment(TELEFONE, store=store)

        assert r['found'] is False
        assert CODIGO not in (r.get('message') or '')

    def test_avisa_o_agente_que_ja_esta_pago(self):
        store = make_store()
        pedido = _pedido(store, StoreOrder.PaymentStatus.PAID)
        _sessao(store, pedido, 'payment_confirmed')

        r = _servico()._get_pending_pix_payment(TELEFONE, store=store)

        assert r.get('paid') is True
        assert 'CE-2610275997' in r['message']
        assert 'pago' in r['message'].lower()

    def test_pedido_pendente_continua_devolvendo_o_pix(self):
        store = make_store()
        pedido = _pedido(store, StoreOrder.PaymentStatus.PENDING)
        _sessao(store, pedido, 'payment_pending')

        r = _servico()._get_pending_pix_payment(TELEFONE, store=store)

        assert r['found'] is True
        assert r['pix_code'] == CODIGO

    def test_sessao_presa_no_pago_mas_outro_pedido_pendente_devolve_o_pendente(self):
        store = make_store()
        pago = _pedido(store, StoreOrder.PaymentStatus.PAID)
        _sessao(store, pago, 'payment_confirmed')
        pendente = _pedido(store, StoreOrder.PaymentStatus.PENDING, numero='CE-2610279999')
        pendente.pix_code = CODIGO + 'NOVO'
        pendente.save(update_fields=['pix_code'])

        r = _servico()._get_pending_pix_payment(TELEFONE, store=store)

        assert r['found'] is True
        assert r['pix_code'] == CODIGO + 'NOVO'


def _handler_pagamento(store):
    from unittest.mock import MagicMock
    from apps.whatsapp.intents.handlers.payment import PaymentStatusHandler
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


@pytest.mark.django_db
class TestJaPagueiComPedidoPago:
    """'Já paguei.' → 'Não encontrei pagamentos pendentes. Quer fazer um pedido
    novo?' Para quem acabou de pagar, a resposta certa é confirmar o pagamento."""

    def test_confirma_o_pagamento_do_pedido_recente(self):
        store = make_store()
        _pedido(store, StoreOrder.PaymentStatus.PAID)

        r = _handler_pagamento(store).handle({'original_message': 'Já paguei.'})

        assert 'CE-2610275997' in r.response_text
        assert 'confirmado' in r.response_text.lower()
        assert 'pedido novo' not in r.response_text.lower()

    def test_sem_pedido_nenhum_continua_igual(self):
        store = make_store()

        r = _handler_pagamento(store).handle({'original_message': 'Já paguei.'})

        assert 'pedido novo' in r.response_text.lower()


def test_texto_ao_cliente_do_pedido_pago_nao_tem_instrucao_ao_agente():
    from apps.agents.services.langchain_service import texto_ao_cliente_do_pix
    texto = texto_ao_cliente_do_pix({
        'found': False, 'paid': True, 'order_number': 'CE-2610275997',
        'message': 'O pedido CE-2610275997 JÁ ESTÁ PAGO. Não envie PIX nem peça pagamento',
    })
    assert 'CE-2610275997' in texto
    assert 'confirmado' in texto.lower()
    assert 'não envie' not in texto.lower()
