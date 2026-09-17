"""IA falhou → o cliente não lê "desculpe"; a conversa vai para o atendente.

17/set/2026, conversa do Francisco (Cê Saladas). O modelo do agente
(deepseek-v4-flash na NVIDIA) parou de responder. Cada mensagem do cliente
esperava ~3 minutos de tentativas e caía no fallback "Desculpe, tive um
problema ao processar sua mensagem. Pode tentar novamente?".

Dois defeitos no mesmo caminho:

1. O "desculpe" é pior que silêncio: pede ao cliente para repetir uma coisa que
   ninguém vai responder. Decisão do dono: quando a IA falha, o bot se cala, a
   conversa passa para humano e o painel é avisado.
2. O modo humano só era conferido ANTES da chamada. Às 10:57 um atendente
   respondeu o Francisco; às 11:00 o "desculpe" saiu por cima dele, porque a
   chamada tinha começado quando a conversa ainda estava no automático.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.handover.models import HandoverRequest
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.tasks import process_message_with_agent

User = get_user_model()

TASKS = 'apps.whatsapp.tasks'


class _Base(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-ia', email='dono-ia@loja.com', password='x',
        )
        self.conta = WhatsAppAccount.objects.create(
            name='Loja IA', phone_number_id='PH_IA', waba_id='WABA_IA',
            phone_number='5563900000100', owner=self.dono,
        )
        self.conversa = Conversation.objects.create(
            account=self.conta, phone_number='5563911112222',
            contact_name='Francisco', mode=Conversation.ConversationMode.AUTO,
        )
        self.mensagem = Message.objects.create(
            account=self.conta, conversation=self.conversa,
            whatsapp_message_id='wamid.IA1', direction='inbound',
            message_type='text', from_number='5563911112222',
            to_number=self.conta.phone_number,
            text_body='Fica quase em frente ao Chambas Gourmet',
        )

    def _rodar(self, resposta_do_agente=None, erro_do_agente=None, antes_de_enviar=None):
        """Roda a tarefa real com a IA e o envio substituídos."""
        def agente(**kwargs):
            if antes_de_enviar:
                antes_de_enviar()
            if erro_do_agente:
                raise erro_do_agente
            return {'response': resposta_do_agente}

        with patch(f'{TASKS}.acquire_lock', return_value=True), \
             patch(f'{TASKS}.release_lock'), \
             patch('apps.automation.services.context_service.AutomationContextService.resolve'), \
             patch('apps.automation.services.context_service.AutomationContextService.get_default_agent',
                   return_value=type('Agente', (), {'id': 'agente-1'})()), \
             patch('apps.automation.services.context_service.AutomationContextService.is_ai_enabled',
                   return_value=True), \
             patch('apps.agents.services.AgentService.get_agent_response', side_effect=agente), \
             patch(f'{TASKS}.send_agent_response') as envio, \
             patch('apps.handover.models.notify_handover_request') as aviso:
            process_message_with_agent.run(str(self.mensagem.id))
        return envio, aviso


class IAFalhouTest(_Base):
    def test_cliente_nao_recebe_desculpe(self):
        envio, _ = self._rodar(erro_do_agente=TimeoutError('Request timed out.'))
        envio.delay.assert_not_called()

    def test_conversa_passa_para_humano(self):
        self._rodar(erro_do_agente=TimeoutError('Request timed out.'))
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.HUMAN)

    def test_painel_recebe_pedido_de_atendimento(self):
        _, aviso = self._rodar(erro_do_agente=TimeoutError('Request timed out.'))
        pedido = HandoverRequest.objects.get(conversation=self.conversa)
        self.assertEqual(pedido.priority, 'high')
        self.assertIn('IA', pedido.reason)
        aviso.assert_called_once()


class AtendenteAssumiuDuranteAEsperaTest(_Base):
    def test_resposta_da_ia_nao_sai_por_cima_do_atendente(self):
        def atendente_assume():
            Conversation.objects.filter(pk=self.conversa.pk).update(
                mode=Conversation.ConversationMode.HUMAN,
            )

        envio, _ = self._rodar(
            resposta_do_agente='Anotado!', antes_de_enviar=atendente_assume,
        )
        envio.delay.assert_not_called()

    def test_ia_respondendo_normal_continua_enviando(self):
        """Âncora: sem isto, 'não enviou' passaria numa tarefa quebrada."""
        envio, _ = self._rodar(resposta_do_agente='Anotado, vou avisar o entregador!')
        envio.delay.assert_called_once()
        self.assertIn('Anotado', envio.delay.call_args[0][2])
