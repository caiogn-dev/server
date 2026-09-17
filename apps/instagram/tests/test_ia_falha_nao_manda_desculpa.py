"""IA falhou no Direct: o cliente NÃO recebe "Desculpe, tive um problema".

Mesma regra do WhatsApp (17/set, conversa do Francisco): quando a IA não
responde, nada vai para o cliente — a conversa fica marcada como não lida para
o atendente assumir. Uma desculpa automática só ensina o cliente que a loja
está quebrada, e ainda pode cair por cima de um atendente que já respondeu.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import Agent
from apps.instagram.models import (
    InstagramAccount, InstagramConversation, InstagramMessage,
)


class IaFalhaNoDirectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ig-ia', email='ig-ia@example.com', password='pass',
        )
        self.agent = Agent.objects.create(name='Caio', status=Agent.AgentStatus.ACTIVE)
        self.account = InstagramAccount.objects.create(
            user=self.user,
            username='loja',
            instagram_business_id='ig-1',
            access_token='token',
            is_active=True,
            auto_response_enabled=True,
            default_agent=self.agent,
        )
        self.conversa = InstagramConversation.objects.create(
            account=self.account,
            participant_id='ig-user-1',
            participant_username='cliente',
            unread_count=0,
        )
        self.mensagem = InstagramMessage.objects.create(
            conversation=self.conversa,
            content='oi, tem salada hoje?',
            is_from_business=False,
        )

    def _rodar(self, efeito):
        from apps.instagram.tasks import process_instagram_dm

        with patch(
            'apps.agents.services.AgentService.get_agent_response', side_effect=efeito,
        ), patch(
            'apps.instagram.services.instagram_direct_service.'
            'InstagramDirectService.send_text_message'
        ) as enviar:
            process_instagram_dm(str(self.mensagem.id))
        return enviar

    def test_ia_quebrou_nao_manda_nada_pro_cliente(self):
        enviar = self._rodar(RuntimeError('APITimeoutError'))

        enviar.assert_not_called()

    def test_ia_quebrou_marca_conversa_pro_atendente(self):
        self._rodar(RuntimeError('APITimeoutError'))

        self.conversa.refresh_from_db()
        self.assertGreater(
            self.conversa.unread_count, 0,
            'conversa precisa aparecer como pendente para alguém responder',
        )

    def test_a_frase_da_desculpa_nao_existe_mais_no_codigo(self):
        from pathlib import Path
        import apps.instagram.tasks as tasks

        fonte = Path(tasks.__file__).read_text(encoding='utf-8')
        self.assertNotIn('Desculpe, tive um problema', fonte)

    def test_resposta_normal_continua_saindo(self):
        from apps.instagram.tasks import process_instagram_dm

        with patch(
            'apps.agents.services.AgentService.get_agent_response',
            return_value={'response': 'Temos sim!'},
        ), patch(
            'apps.instagram.services.instagram_direct_service.'
            'InstagramDirectService.send_text_message'
        ) as enviar:
            process_instagram_dm(str(self.mensagem.id))

        enviar.assert_called_once()
        self.assertIn('Temos sim!', enviar.call_args[0])
