"""A IA precisa lembrar do que o BOT (handlers) disse, não só do que ela disse.

28/09/2026, Cê Saladas, 11:47: o handler respondeu "🥗 Monte sua Salada
R$ 9.99". A cliente: "2 dessa promoção". A IA, que só tinha na memória os
próprios turnos, perguntou "qual promoção?". Para a cliente é UMA conversa;
para a IA eram duas — a dela e a do bot de regex, que ela nunca via.

O turno do handler/template entra na mesma memória Redis do agente, no
invólucro de `process_message`, pelo mesmo motivo do IntentLog: lá dentro há
dezenas de `return`.
"""
import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import Agent
from apps.automation.models import CompanyProfile
from apps.automation.services.unified_service import ResponseSource, UnifiedResponse, UnifiedService
from apps.stores.models import Store

User = get_user_model()


class MemoriaDoAgenteVeOBotTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-mem', password='x')
        self.store = Store.objects.create(name='Loja MEM', slug='loja-mem', owner=dono, status='active')
        self.agent = Agent.objects.create(name='Atendente', provider=Agent.AgentProvider.NVIDIA)
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.use_ai_agent = True
        self.profile.default_agent = self.agent
        self.profile.save()
        self.memoria = Mock()

    def _servico(self, use_llm=True):
        servico = UnifiedService.__new__(UnifiedService)
        servico.company = self.profile
        servico.store = self.store
        servico.conversation = Mock(id=uuid.uuid4(), phone_number='5563999990000')
        servico.account = None
        servico.agent = self.agent
        servico.use_llm = use_llm
        servico.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}
        servico.phone_number = '5563999990000'
        return servico

    def _rodar(self, resposta, use_llm=True):
        servico = self._servico(use_llm)
        with patch.object(UnifiedService, '_processar_mensagem', return_value=resposta), \
             patch.object(UnifiedService, '_registrar_intencao'), \
             patch('apps.agents.services.langchain_service.memoria_do_agente', return_value=self.memoria) as m:
            servico.process_message('2 dessa promoção')
            return m

    def test_resposta_de_handler_entra_na_memoria_do_agente(self):
        m = self._rodar(UnifiedResponse(content='🥗 *Monte sua Salada*\n💰 R$ 9.99', source=ResponseSource.HANDLER))

        m.assert_called_once()
        self.assertIs(m.call_args.args[0], self.agent)
        self.memoria.add_user_message.assert_called_once_with('2 dessa promoção')
        self.memoria.add_ai_message.assert_called_once_with('🥗 *Monte sua Salada*\n💰 R$ 9.99')

    def test_resposta_do_proprio_llm_nao_e_gravada_duas_vezes(self):
        self._rodar(UnifiedResponse(content='Claro!', source=ResponseSource.LLM))
        self.memoria.add_ai_message.assert_not_called()

    def test_sem_agente_conversando_nao_toca_na_memoria(self):
        m = self._rodar(UnifiedResponse(content='Oi', source=ResponseSource.HANDLER), use_llm=False)
        m.assert_not_called()

    def test_resposta_vazia_ou_suprimida_nao_e_gravada(self):
        self._rodar(UnifiedResponse(content='', source=ResponseSource.SUPPRESSED))
        self._rodar(None)
        self.memoria.add_ai_message.assert_not_called()
