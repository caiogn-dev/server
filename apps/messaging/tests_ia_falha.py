"""IA falhou no Messenger: o cliente NÃO recebe "Desculpe, tive um problema".

Irmão de apps/instagram/tests/test_ia_falha_nao_manda_desculpa.py — mesma regra
decidida em 17/set para o WhatsApp.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import Agent
from apps.messaging.models import (
    MessengerAccount, MessengerConversation, MessengerMessage,
)


class IaFalhaNoMessengerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='msg-ia', email='msg-ia@example.com', password='pass',
        )
        self.agent = Agent.objects.create(name='Caio', status=Agent.AgentStatus.ACTIVE)
        self.account = MessengerAccount.objects.create(
            user=self.user,
            page_id='page-ia',
            page_name='Loja',
            page_access_token='token',
            is_active=True,
            auto_response_enabled=True,
            default_agent=self.agent,
        )
        self.conversa = MessengerConversation.objects.create(
            account=self.account,
            psid='psid-ia',
            participant_name='Cliente',
            unread_count=0,
        )
        self.mensagem = MessengerMessage.objects.create(
            conversation=self.conversa,
            message_type='TEXT',
            content='tem entrega hoje?',
            is_from_page=False,
        )

    def _rodar(self, efeito):
        from apps.messaging.tasks import process_messenger_dm

        with patch(
            'apps.agents.services.AgentService.get_agent_response', side_effect=efeito,
        ), patch('apps.messaging.services.MessengerService.send_message') as enviar:
            process_messenger_dm(str(self.mensagem.id))
        return enviar

    def test_ia_quebrou_nao_manda_nada_pro_cliente(self):
        enviar = self._rodar(RuntimeError('APITimeoutError'))

        enviar.assert_not_called()

    def test_ia_quebrou_marca_conversa_pro_atendente(self):
        self._rodar(RuntimeError('APITimeoutError'))

        self.conversa.refresh_from_db()
        self.assertGreater(self.conversa.unread_count, 0)

    def test_a_frase_da_desculpa_nao_existe_mais_no_codigo(self):
        from pathlib import Path
        import apps.messaging.tasks as tasks

        fonte = Path(tasks.__file__).read_text(encoding='utf-8')
        self.assertNotIn('Desculpe, tive um problema', fonte)

    def test_resposta_normal_continua_saindo(self):
        from apps.messaging.tasks import process_messenger_dm

        with patch(
            'apps.agents.services.AgentService.get_agent_response',
            return_value={'response': 'Temos sim!'},
        ), patch('apps.messaging.services.MessengerService.send_message') as enviar:
            process_messenger_dm(str(self.mensagem.id))

        enviar.assert_called_once()
        self.assertEqual(enviar.call_args[0][1], {'text': 'Temos sim!'})
