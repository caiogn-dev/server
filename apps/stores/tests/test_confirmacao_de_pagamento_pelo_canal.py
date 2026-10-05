"""Confirmação de pagamento no WhatsApp passa pelo canal das automáticas.

Dono, 05/10: aviso de pedido é mensagem normal e só com janela de 24 h aberta.
Este caminho ia direto ao MessageService, sem olhar a janela nem o modo humano.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.api.webhooks import MercadoPagoWebhookView
from apps.stores.models import Store, StoreOrder

User = get_user_model()


class ConfirmacaoPeloCanalTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='ow-conf', email='ow-conf@t.com', password='x')
        self.store = Store.objects.create(name='Loja C', slug='loja-conf', owner=owner, status='active')
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Ana', customer_phone='63984301666',
            subtotal=Decimal('40'), total=Decimal('40'),
        )

    def test_sai_pelo_canal_com_evento_de_pagamento(self):
        conta = MagicMock()
        with patch.object(Store, 'get_whatsapp_account', return_value=conta), \
                patch('apps.automation.mensageiro.enviar_texto') as enviar:
            MercadoPagoWebhookView()._send_payment_confirmation_whatsapp(self.pedido)

        args, kwargs = enviar.call_args
        self.assertIs(args[0], conta)
        self.assertEqual(args[1], '5563984301666')
        self.assertIn('Pagamento Confirmado', args[2])
        self.assertEqual(kwargs['evento'], 'order_paid')

    def test_janela_fechada_nao_chama_a_meta(self):
        conta = MagicMock()
        with patch.object(Store, 'get_whatsapp_account', return_value=conta), \
                patch('apps.automation.mensageiro.janela.aberta', return_value=False), \
                patch('apps.whatsapp.services.message_service.MessageService.send_text_message') as texto, \
                patch('apps.automation.mensageiro.politica.silenciado', return_value=False):
            MercadoPagoWebhookView()._send_payment_confirmation_whatsapp(self.pedido)
        texto.assert_not_called()
