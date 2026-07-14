"""Modo restrito: allow-list de intents no CompanyProfile.settings.

Caso de uso (Pastita 14/jul): dono quer o bot DESLIGADO — nada de IA, nada de
fluxo interativo de pedido, nada de mensagem automática — respondendo apenas
intents informativas explicitamente liberadas (cardápio, horário) e mantendo
os disparos transacionais de status de pedido (outbound, fora deste pipeline).

Contrato:
- profile.settings['allowed_intents'] = ['menu_request', ...] ativa o modo.
- Intent fora da lista → UnifiedResponse(source=SUPPRESSED) — silêncio, sem
  fallback de LLM e sem alerta de MESSAGE DROPPED no webhook_service.
- Cliques interativos e localização (fluxos de bot) → suprimidos no modo.
- Sem allowed_intents → comportamento atual intacto.
"""
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services.unified_service import (
    ResponseSource, UnifiedResponse, UnifiedService,
)
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount


def _mk_account(**kw):
    return WhatsAppAccount.objects.create(
        name='Pastita', phone_number_id=kw.pop('phone_number_id', 'PH1'),
        waba_id='WABA1', **kw,
    )


class RestrictedIntentsModeTest(TestCase):
    def setUp(self):
        self.account = _mk_account()
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563999990000',
        )
        # O signal post_save de WhatsAppAccount já cria o CompanyProfile
        self.profile = CompanyProfile.objects.get(account=self.account)
        self.profile.settings = {'allowed_intents': ['menu_request', 'business_hours']}
        self.profile.save(update_fields=['settings'])
        # O signal deixa o profile pré-settings cacheado na instância da conta;
        # produção sempre busca a conta fresca do banco — reproduzir isso aqui.
        self.account = WhatsAppAccount.objects.get(pk=self.account.pk)

    def _service(self):
        return UnifiedService(self.account, self.conversation, use_llm=False)

    def test_greeting_is_suppressed(self):
        resp = self._service().process_message('oi, tudo bem?')
        self.assertIsInstance(resp, UnifiedResponse)
        self.assertEqual(resp.source, ResponseSource.SUPPRESSED)

    def test_interactive_reply_is_suppressed(self):
        resp = self._service().process_message(
            '', interactive_reply={'type': 'button_reply', 'id': 'x', 'title': 'Montar salada'},
        )
        self.assertIsInstance(resp, UnifiedResponse)
        self.assertEqual(resp.source, ResponseSource.SUPPRESSED)

    def test_allowed_intent_still_responds(self):
        resp = self._service().process_message('qual o horário de funcionamento?')
        self.assertIsInstance(resp, UnifiedResponse)
        self.assertNotEqual(resp.source, ResponseSource.SUPPRESSED)

    def test_without_allowed_intents_behavior_unchanged(self):
        self.profile.settings = {}
        self.profile.save(update_fields=['settings'])
        resp = self._service().process_message('oi, tudo bem?')
        # Sem modo restrito, saudação segue o pipeline normal (nunca suprimida)
        if resp is not None:
            self.assertNotEqual(resp.source, ResponseSource.SUPPRESSED)


class WebhookDispatchSuppressedTest(TestCase):
    """Resposta SUPPRESSED conta como tratada: sem fallback e sem MESSAGE DROPPED."""

    def test_dispatch_marks_suppressed_as_sent(self):
        from unittest import mock
        from apps.whatsapp.services.webhook_service import WebhookService

        svc = WebhookService()
        suppressed = UnifiedResponse(content='', source=ResponseSource.SUPPRESSED)
        event = mock.Mock()
        message = mock.Mock()
        sent, err = svc._dispatch_orchestrator_response(
            event, message,
            orchestrator_response=suppressed,
            orchestrator_error=None,
            orchestrator_ms=1.0,
            timed_out=False,
        )
        self.assertTrue(sent, 'SUPPRESSED deve contar como resposta tratada')
        self.assertIsNone(err)
