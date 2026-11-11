"""Bot da Cê Saladas conversou 12 minutos com outro robô (05/nov/2026).

Uma campanha foi para +55 16 3523-0811, que é um assistente automático. Ele
respondeu "O assistente está disponível apenas para lojas selecionadas", o
nosso bot respondeu "Oi! Que bom que entrou em contato…", ele repetiu, e
assim 45 vezes cada lado, a cada ~6 s — até alguém do outro lado parar.

Contrato: a MESMA mensagem (não curta) chegando pela 3ª vez em 10 min na
mesma conversa é eco de robô — o bot para de responder. Mensagem curta
("sim", "ok", "1") repete legitimamente num checkout e nunca é calada.
"""
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.automation.services.sem_repeticao import mensagem_em_eco

ROBO = 'O assistente está disponível apenas para lojas selecionadas'

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOCMEM)
class MensagemEmEcoTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_terceira_repeticao_e_eco(self):
        self.assertFalse(mensagem_em_eco('conv-1', ROBO))
        self.assertFalse(mensagem_em_eco('conv-1', ROBO))
        self.assertTrue(mensagem_em_eco('conv-1', ROBO))
        self.assertTrue(mensagem_em_eco('conv-1', ROBO))

    def test_variacao_de_caixa_e_espaco_conta_como_a_mesma(self):
        mensagem_em_eco('conv-1', ROBO)
        mensagem_em_eco('conv-1', ROBO.upper())
        self.assertTrue(mensagem_em_eco('conv-1', f'  {ROBO}  '))

    def test_mensagem_curta_nunca_e_eco(self):
        for _ in range(6):
            self.assertFalse(mensagem_em_eco('conv-1', 'sim'))

    def test_conversas_diferentes_nao_se_misturam(self):
        mensagem_em_eco('conv-1', ROBO)
        mensagem_em_eco('conv-1', ROBO)
        self.assertFalse(mensagem_em_eco('conv-2', ROBO))


@override_settings(CACHES=LOCMEM)
class UnifiedServiceParaDeResponderAoEcoTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _svc(self):
        from apps.automation.services.unified_service import UnifiedService
        svc = UnifiedService.__new__(UnifiedService)
        svc.conversation = MagicMock(id='conv-robo')
        svc.company = None
        svc.agent = None
        svc._comando_de_vigia = MagicMock(return_value=None)
        svc._registrar_intencao = MagicMock()
        svc._memorizar_turno_do_bot = MagicMock()
        svc._processar_mensagem = MagicMock(
            return_value=MagicMock(content='Oi! Que bom que entrou em contato', metadata={}),
        )
        return svc

    def test_terceira_vez_nao_processa_nem_responde(self):
        svc = self._svc()
        svc.process_message(ROBO)
        svc.process_message(ROBO)
        terceira = svc.process_message(ROBO)
        self.assertEqual(svc._processar_mensagem.call_count, 2)
        self.assertEqual(getattr(terceira.source, 'value', None), 'suppressed')

    def test_clique_em_botao_nao_conta(self):
        svc = self._svc()
        for _ in range(4):
            svc.process_message(ROBO, interactive_reply={'id': 'x', 'title': ROBO})
        self.assertEqual(svc._processar_mensagem.call_count, 4)
