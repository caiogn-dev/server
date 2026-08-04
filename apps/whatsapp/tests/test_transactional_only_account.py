"""Contas transacionais (só OTP/notificação) não podem rodar o bot.

O número global do Cardapidex (+1 555-404-4637) existe apenas para enviar OTP.
Quando alguém responde nele, a mensagem deve entrar no inbox mas NENHUMA
resposta automática pode sair — nem handler/template, nem LLM.

Contrato: WhatsAppAccount.metadata['transactional_only'] = True desliga o
pipeline de automação para aquela conta.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.models.webhook import WebhookEvent
from apps.whatsapp.services.webhook_service import WebhookService


class TransactionalOnlyAccountTest(TestCase):
    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cardapidex (global)',
            phone_number_id='PHOTP',
            waba_id='WABAOTP',
            metadata={'transactional_only': True},
        )
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563991386719',
        )
        self.message = Message.objects.create(
            account=self.account,
            conversation=self.conversation,
            whatsapp_message_id='wamid.OTP1',
            direction='inbound',
            message_type='text',
            from_number='5563991386719',
            to_number='+15554044637',
            text_body='Oi',
        )
        self.event = WebhookEvent.objects.create(
            account=self.account,
            event_id='evt-otp-1',
            event_type=WebhookEvent.EventType.MESSAGE,
            payload={'message': {'id': 'wamid.OTP1'}, 'contact': {}},
        )
        self.service = WebhookService()

    def test_conta_transacional_nao_roda_orquestrador(self):
        with patch.object(WebhookService, '_run_orchestrator_with_timeout') as orch:
            self.service.post_process_inbound_message(self.event, self.message)
        orch.assert_not_called()

    def test_conta_normal_continua_rodando_orquestrador(self):
        self.account.metadata = {}
        self.account.save(update_fields=['metadata'])
        self.event.refresh_from_db()

        with patch.object(
            WebhookService, '_run_orchestrator_with_timeout',
            return_value=(None, None, 0, False),
        ) as orch:
            self.service.post_process_inbound_message(self.event, self.message)
        orch.assert_called_once()
