"""Pagamento a menor não pode ser mudo.

A trava está certa: PIX de R$ 38,95 num pedido de R$ 43,28 NÃO quita o
pedido (fica `processing`). O defeito era ninguém saber — o pedido só parava
(Leani CE-2609038526, Priscila CE-2609021794, esta cancelada com dinheiro dentro).

Agora a loja recebe `order.payment_partial` no WebSocket com quanto entrou e
quanto falta. E o consumer precisa ter handler para TODO tipo que o
broadcaster emite: sem `order_paid`, o Channels derruba a mensagem com
"No handler for message type" e o painel nunca via PIX confirmado ao vivo.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.consumers import OrderConsumer
from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services import realtime_service
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class PagamentoAMenorAvisaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-pm', password='x')
        self.store = Store.objects.create(name='Loja PM', slug='loja-pm', owner=dono, status='active')
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Leani', customer_phone='5563999990001',
            status='pending', payment_status='pending', payment_method='pix',
            subtotal=Decimal('43.28'), total=Decimal('43.28'),
        )

    def _cobranca(self, valor):
        return StorePayment.objects.create(
            order=self.pedido, store=self.store, amount=Decimal(valor),
            payment_method='pix', status=StorePayment.PaymentStatus.PENDING,
            external_id=f'mp-{valor}',
        )

    def test_parcial_continua_travado_e_avisa_a_loja(self):
        cobranca = self._cobranca('38.95')
        with patch.object(realtime_service, 'broadcast_order_event') as avisar:
            with self.captureOnCommitCallbacks(execute=True):
                CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
        self.pedido.refresh_from_db()
        assert self.pedido.payment_status == 'processing'
        parciais = [c for c in avisar.call_args_list if c.kwargs.get('event_type') == 'order.payment_partial']
        assert len(parciais) == 1, avisar.call_args_list
        extra = parciais[0].kwargs['extra']
        assert Decimal(extra['amount_paid']) == Decimal('38.95')
        assert Decimal(extra['amount_due']) == Decimal('4.33')

    def test_pagamento_cheio_nao_dispara_aviso_de_parcial(self):
        cobranca = self._cobranca('43.28')
        with patch.object(realtime_service, 'broadcast_order_event') as avisar, \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'):
            with self.captureOnCommitCallbacks(execute=True):
                CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
        tipos = [c.kwargs.get('event_type') for c in avisar.call_args_list]
        assert 'order.payment_partial' not in tipos


class ContratoDoTempoRealTest(TestCase):
    def test_parcial_e_evento_suportado(self):
        assert 'order.payment_partial' in realtime_service.SUPPORTED_ORDER_EVENTS

    def test_consumer_tem_handler_para_todo_evento_emitido(self):
        for tipo in realtime_service.SUPPORTED_ORDER_EVENTS:
            metodo = tipo.replace('.', '_')
            assert hasattr(OrderConsumer, metodo), f'OrderConsumer sem handler {metodo}'

    def test_payload_leva_os_valores_extras(self):
        dono = User.objects.create_user(username='dono-pl', password='x')
        store = Store.objects.create(name='Loja PL', slug='loja-pl', owner=dono, status='active')
        pedido = StoreOrder.objects.create(
            store=store, customer_name='X', customer_phone='5563999990002',
            subtotal=Decimal('10'), total=Decimal('10'),
        )
        enviados = []

        class Camada:
            async def group_send(self, grupo, msg):
                enviados.append(msg)

        with patch.object(realtime_service, 'get_channel_layer', return_value=Camada()):
            realtime_service.broadcast_order_event(
                pedido, event_type='order.payment_partial',
                extra={'amount_paid': '4.00', 'amount_due': '6.00'},
            )
        assert enviados[0]['type'] == 'order.payment_partial'
        assert enviados[0]['amount_due'] == '6.00'
