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


class EcoNaConversaCanonicaTest(TestCase):
    """O eco não pode abrir uma segunda conversa por causa do nono dígito.

    Produção (set/2026): 12 clientes com duas conversas na mesma conta em 10
    dias. Ex.: `5563984409679` (a real, com mensagens do cliente) e
    `556384409679`, criada minutos depois só com outbound text/reaction/
    revoke/edit/video — o eco do que a loja digitou no app Business. A Meta
    manda o `to` sem o 9 e o eco fazia `get_or_create` com o número cru.
    """

    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Conta Echo 9', phone_number_id='PHECHO', waba_id='WABA1',
        )
        self.service = WebhookService()

    def _eco(self, para, wamid='wamid.ECO9'):
        payload = echo_payload(msg_id=wamid)
        payload['entry'][0]['changes'][0]['value']['message_echoes'][0]['to'] = para
        return payload

    def test_eco_sem_o_nove_cai_na_conversa_que_tem_o_nove(self):
        real = Conversation.objects.create(account=self.account, phone_number='5563984409679')
        Message.objects.create(
            account=self.account, conversation=real, whatsapp_message_id='wamid.IN1',
            direction='inbound', message_type='text', from_number='5563984409679',
            to_number='556399990000', text_body='oi',
        )

        self.service.process_webhook(self._eco('556384409679'), headers={})

        msg = Message.objects.get(whatsapp_message_id='wamid.ECO9')
        self.assertEqual(msg.conversation_id, real.id)
        self.assertEqual(Conversation.objects.filter(account=self.account).count(), 1)

    def test_sem_conversa_cria_com_o_telefone_normalizado(self):
        self.service.process_webhook(self._eco('556384409679'), headers={})

        conversas = list(Conversation.objects.filter(account=self.account))
        self.assertEqual(len(conversas), 1)
        self.assertEqual(conversas[0].phone_number, '5563984409679')
