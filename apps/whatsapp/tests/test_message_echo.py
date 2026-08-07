"""Eco de mensagens do app WhatsApp Business (COEX, campo smb_message_echoes).

O lojista responde clientes pelo APP; sem tratar o eco, essas mensagens nunca
apareciam no inbox do painel. Contrato:

- process_webhook com field=smb_message_echoes cria Message OUTBOUND na
  conversa do cliente (to), com dedupe por whatsapp_message_id.
- NÃO cria WebhookEvent de MESSAGE (o bot não pode responder ao próprio eco).
"""
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.models.webhook import WebhookEvent
from apps.whatsapp.services.webhook_service import WebhookService


def echo_payload(msg_id='wamid.ECHO1', text='Chego em 10min!'):
    return {
        'entry': [{
            'id': 'WABA1',
            'changes': [{
                'field': 'smb_message_echoes',
                'value': {
                    'messaging_product': 'whatsapp',
                    'metadata': {'phone_number_id': 'PHECHO', 'display_phone_number': '556399990000'},
                    'message_echoes': [{
                        'id': msg_id,
                        'from': '556399990000',
                        'to': '5563988887777',
                        'timestamp': '1722550000',
                        'type': 'text',
                        'text': {'body': text},
                    }],
                },
            }],
        }],
    }


class MessageEchoTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Conta Echo', phone_number_id='PHECHO', waba_id='WABA1',
        )
        self.service = WebhookService()

    def test_echo_vira_mensagem_outbound_na_conversa(self):
        self.service.process_webhook(echo_payload(), headers={})
        msg = Message.objects.get(whatsapp_message_id='wamid.ECHO1')
        self.assertEqual(msg.direction, 'outbound')
        self.assertEqual(msg.text_body, 'Chego em 10min!')
        self.assertEqual(msg.to_number, '5563988887777')
        conv = Conversation.objects.get(account=self.account, phone_number='5563988887777')
        self.assertEqual(msg.conversation_id, conv.id)
        self.assertIsNotNone(conv.last_message_at)

    def test_eco_duplicado_nao_duplica(self):
        self.service.process_webhook(echo_payload(), headers={})
        self.service.process_webhook(echo_payload(), headers={})
        self.assertEqual(Message.objects.filter(whatsapp_message_id='wamid.ECHO1').count(), 1)

    def test_eco_nao_gera_webhook_event_de_message(self):
        # Conta ANTES e DEPOIS: o exists() global via evento de outra suíte
        # no banco de teste compartilhado e falhava sozinho.
        antes = WebhookEvent.objects.filter(event_type=WebhookEvent.EventType.MESSAGE).count()
        self.service.process_webhook(echo_payload(), headers={})
        depois = WebhookEvent.objects.filter(event_type=WebhookEvent.EventType.MESSAGE).count()
        self.assertEqual(depois, antes, 'eco do WhatsApp não pode virar WebhookEvent de mensagem')
