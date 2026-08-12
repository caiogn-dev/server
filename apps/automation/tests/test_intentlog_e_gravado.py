"""A tela "Intenções" nunca teve dado porque ninguém nunca gravou nada.

O `IntentLog` existe desde o começo — com campo para intenção, método,
confiança, handler, tempo de processamento e resposta. A API existe. A tela do
painel existe. E `IntentLog.objects.create` **não aparece em lugar nenhum do
código**: em produção a tabela tem 0 linhas, permanentemente.

O pipeline já calcula tudo isso a cada mensagem — ele até emite um log de
texto no fim (`unified.intent`, `unified.source`, `unified.duration_ms`) que
morre no stdout do container. Aqui esse mesmo dado passa a ser persistido.

O log é escrito num INVÓLUCRO de `process_message`, não espalhado pelos
caminhos internos: a função tem dezenas de `return` (atalho de localização,
checkout pendente, modo humano, erro…) e gravar em cada um garantiria que
algum ficasse de fora — que é exatamente como uma tela nasce meio vazia.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, IntentLog
from apps.automation.services.unified_service import (
    ResponseSource,
    UnifiedResponse,
    UnifiedService,
)
from apps.stores.models import Store

User = get_user_model()


class IntentLogGravadoTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-il', password='x')
        self.store = Store.objects.create(
            name='Loja IL', slug='loja-il', owner=dono, status='active',
        )
        self.profile = CompanyProfile.objects.get(store=self.store)

    def _servico(self):
        servico = UnifiedService.__new__(UnifiedService)
        servico.company = self.profile
        servico.store = self.store
        servico.conversation = None
        servico.account = None
        servico.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}
        servico.phone_number = '5563999990000'
        return servico

    def _rodar(self, resposta):
        servico = self._servico()
        with patch.object(UnifiedService, '_processar_mensagem', return_value=resposta):
            return servico.process_message('quero ver o cardápio')

    def test_grava_uma_linha_por_mensagem(self):
        resposta = UnifiedResponse(
            content='Aqui está o cardápio!',
            source=ResponseSource.HANDLER,
            metadata={'intent': 'menu_request', 'handler': 'MenuHandler'},
        )

        devolvido = self._rodar(resposta)

        self.assertIs(devolvido, resposta)  # o invólucro não muda a resposta
        log = IntentLog.objects.get()
        self.assertEqual(log.company_id, self.profile.id)
        self.assertEqual(log.intent_type, 'menu_request')
        self.assertEqual(log.handler_used, 'MenuHandler')
        self.assertEqual(log.message_text, 'quero ver o cardápio')
        self.assertEqual(log.response_text, 'Aqui está o cardápio!')
        self.assertEqual(log.phone_number, '5563999990000')
        # Com o processamento mockado a duração arredonda para 0.0 — o que
        # importa aqui é o campo ser preenchido, não o valor.
        self.assertIsNotNone(log.processing_time_ms)
        self.assertGreaterEqual(log.processing_time_ms, 0)

    def test_registra_de_onde_veio_a_resposta(self):
        """Saber que 30% cai em fallback é o valor da tela."""
        self._rodar(UnifiedResponse(content='Não entendi', source=ResponseSource.FALLBACK))

        self.assertEqual(IntentLog.objects.get().metadata['source'], 'fallback')

    def test_resposta_do_llm_marca_o_metodo_como_llm(self):
        self._rodar(UnifiedResponse(
            content='Claro!', source=ResponseSource.LLM, metadata={'intent': 'other'},
        ))

        self.assertEqual(IntentLog.objects.get().method, IntentLog.MethodType.LLM)

    def test_silencio_tambem_e_registrado(self):
        """Mensagem que o bot decidiu NÃO responder é justamente o que a dona
        precisa ver — senão a tela só mostra o que deu certo."""
        self._rodar(None)

        log = IntentLog.objects.get()
        self.assertEqual(log.response_text, '')
        self.assertEqual(log.intent_type, 'sem_resposta')

    def test_falha_ao_gravar_nao_derruba_a_resposta_do_cliente(self):
        """Log é observabilidade: nunca pode custar a resposta ao cliente."""
        resposta = UnifiedResponse(content='oi', source=ResponseSource.TEMPLATE)
        servico = self._servico()

        with patch.object(UnifiedService, '_processar_mensagem', return_value=resposta), \
             patch('apps.automation.models.IntentLog.objects.create', side_effect=Exception('boom')):
            devolvido = servico.process_message('oi')

        self.assertIs(devolvido, resposta)

    def test_sem_company_nao_tenta_gravar(self):
        servico = self._servico()
        servico.company = None
        resposta = UnifiedResponse(content='oi', source=ResponseSource.TEMPLATE)

        with patch.object(UnifiedService, '_processar_mensagem', return_value=resposta):
            servico.process_message('oi')

        self.assertEqual(IntentLog.objects.count(), 0)
