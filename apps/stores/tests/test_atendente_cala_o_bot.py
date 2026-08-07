"""Quando o atendente responde pelo painel, o bot tem que calar a boca.

Este é o bug que o dono relatou primeiro, em 06/ago, olhando a conversa da
Margô: ele assumiu o atendimento e digitou as respostas, e o bot continuou
respondendo por cima dele —

    dono:     "Oii"
    dono:     "Bom dia!"
    cliente:  "Bom dia"
    BOT:      "Oi, Margô! 😊 Você tem itens no carrinho. Quer continuar?"
    cliente:  "Pagar no crédito"
    BOT:      "Como posso te ajudar? 👇"

O gate de modo humano existia e funcionava (`_should_suppress_for_human_mode`),
mas nunca era acionado: NADA trocava `conversation.mode` para `human` quando o
operador respondia. O modo só mudava pelo botão explícito de handover no
painel, que ninguém aperta no meio de um atendimento.

Responder JÁ É assumir o atendimento. O modo tem que seguir o gesto, não
exigir um segundo clique.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount

User = get_user_model()


class RespostaManualAssumeAConversaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='operador', password='x', email='operador@real.com',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Operador', phone_number_id='4001', waba_id='4002',
            access_token='t', phone_number='5563000000040',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number='556781081742',
            contact_name='Margô', mode=Conversation.ConversationMode.AUTO,
        )

    def _enviar(self, texto='Oii'):
        from apps.whatsapp.api.views import MessageViewSet

        falso = Message(
            account=self.account, conversation=self.conversa,
            whatsapp_message_id='wamid-manual', direction='outbound',
            message_type='text', status='sent',
            from_number='5563000000040', to_number=self.conversa.phone_number,
            text_body=texto,
        )
        falso.save()

        rf = APIRequestFactory(SERVER_NAME='localhost')
        req = rf.post('/x', {
            'account_id': str(self.account.id),
            'to': self.conversa.phone_number,
            'text': texto,
        }, format='json')
        force_authenticate(req, user=self.user)

        with patch(
            'apps.whatsapp.services.message_service.MessageService.send_text_message',
            return_value=falso,
        ):
            return MessageViewSet.as_view({'post': 'send_text'})(req)

    def test_responder_pelo_painel_passa_a_conversa_para_humano(self):
        resp = self._enviar()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.conversa.refresh_from_db()
        self.assertEqual(
            self.conversa.mode, Conversation.ConversationMode.HUMAN,
            'o atendente respondeu e o bot continuou solto na conversa',
        )

    def test_conversa_ja_em_modo_humano_continua_humana(self):
        self.conversa.mode = Conversation.ConversationMode.HUMAN
        self.conversa.save(update_fields=['mode'])
        self._enviar('mais uma')
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.HUMAN)

    def test_envio_do_bot_nao_muda_o_modo(self):
        """O bot também manda mensagem — só o gesto do OPERADOR assume.

        `MessageService` é usado pelos dois: pelo pipeline automático e pelo
        painel. Se a troca de modo morasse no service, o próprio bot se
        silenciaria ao responder.
        """
        from apps.whatsapp.services.message_service import MessageService

        # O caminho do bot passa pelo service, nunca pela view autenticada.
        MessageService()._get_or_create_conversation(
            self.account, self.conversa.phone_number,
        )

        self.conversa.refresh_from_db()
        self.assertEqual(
            self.conversa.mode, Conversation.ConversationMode.AUTO,
            'o bot se calou sozinho ao responder',
        )
