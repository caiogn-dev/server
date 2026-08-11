"""O bot não pode falar por cima de quem está atendendo. 11/ago/2026.

Duas conversas reais no mesmo dia, dois furos diferentes no modo humano:

1) Damery (13:32→13:33). O dono assumiu pelo painel às 13:32:13 e digitou três
   mensagens sobre o endereço. Às 13:33:37 a cliente mandou a LOCALIZAÇÃO:

     webhook   → "Human mode bypass for deterministic order flow"  (deixou passar)
     unified   → "Conversation in human mode — skipping automation" (calou)
     pipeline  → MESSAGE DROPPED
     bot       → "Recebi sua mensagem, mas não consegui responder direito
                  agora 😕 / 👤 Falar com atendente"

   Mesma divergência de camadas que matou a avaliação da Dyana em 10/ago, só
   que pela porta da localização: o webhook liberava QUALQUER localização, e o
   orquestrador só libera quando existe checkout esperando endereço. O que o
   webhook deixa passar e o orquestrador engole vira último recurso — o bot
   entrando na conversa no pior momento possível.

2) Diogo (13:04 e 13:18). O dono respondeu pelo APP do WhatsApp Business (COEX),
   não pelo painel. O eco chega em `_handle_message_echo`, que gravava a
   mensagem e não mexia no modo: a conversa seguia 'auto' e o bot respondeu por
   cima do dono duas vezes, com botões de cardápio.

   Responder pelo painel já assumia a conversa desde 06/ago
   (`MessageViewSet._assumir_atendimento`). Responder pelo app não. Para o
   cliente é o mesmo gesto — e em COEX o app é onde o dono realmente atende.
"""
import logging
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.automation.models import CompanyProfile, CustomerSession
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService

User = get_user_model()

TELEFONE = '5563991199575'
LOCALIZACAO = {'lat': -10.2055997, 'lng': -48.3364334}


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dona-ce', email='dona@cesaladas.com', password='x',
        )
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-atropelo',
            owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_ATROPELO', waba_id='WABA_ATROPELO',
            phone_number='5563991386719',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number=TELEFONE, contact_name='Damery',
            mode=Conversation.ConversationMode.HUMAN,
        )

    def _mensagem(self):
        msg = MagicMock()
        msg.id = 'msg-loc'
        msg.conversation = self.conversa
        return msg

    def _contexto(self):
        from apps.automation.services.context_service import AutomationContext

        return AutomationContext(
            store=self.store, profile=self.profile,
            account=self.account, conversation=self.conversa,
        )

    def _sessao_esperando_endereco(self):
        return CustomerSession.objects.create(
            company=self.profile, phone_number=TELEFONE,
            session_id=f'whatsapp_{TELEFONE}_addr',
            status=CustomerSession.SessionStatus.CHECKOUT,
            cart_data={'waiting_for_address': True},
        )


class LocalizacaoNoModoHumanoTest(_Base):
    """O caso da Damery: localização não é passe livre."""

    def _webhook_suprime(self):
        return WebhookService()._should_suppress_for_human_mode(
            self._mensagem(), None, LOCALIZACAO, context=self._contexto(),
        )

    def _orquestrador_libera(self):
        service = UnifiedService(self.account, self.conversa, use_llm=False)
        return service._is_human_mode_transactional_step('', None, LOCALIZACAO)

    def test_localizacao_sem_checkout_pendente_e_suprimida(self):
        """Não havia pedido esperando endereço: o atendente estava resolvendo na mão."""
        self.assertTrue(self._webhook_suprime())

    def test_localizacao_com_checkout_pendente_continua_passando(self):
        """O bot pediu o endereço antes do handover — terminar o pedido é dele."""
        self._sessao_esperando_endereco()
        self.assertFalse(self._webhook_suprime())

    def test_paridade_com_o_orquestrador_sem_sessao(self):
        """Deixar passar e não responder é o que produz o último recurso."""
        self.assertEqual(not self._webhook_suprime(), self._orquestrador_libera())

    def test_paridade_com_o_orquestrador_com_sessao(self):
        self._sessao_esperando_endereco()
        self.assertEqual(not self._webhook_suprime(), self._orquestrador_libera())

    def test_fora_do_modo_humano_localizacao_nao_e_suprimida(self):
        self.conversa.mode = Conversation.ConversationMode.AUTO
        self.conversa.save(update_fields=['mode'])
        self.assertFalse(self._webhook_suprime())


class UltimoRecursoRespeitaOAtendenteTest(_Base):
    """A defesa contra silêncio não pode virar fala por cima do atendente."""

    def _evento(self):
        ev = MagicMock()
        ev.account.id = str(self.account.id)
        return ev

    def _msg_real(self, conversa):
        msg = MagicMock()
        msg.id = 'msg-ultimo'
        msg.conversation = conversa
        msg.from_number = TELEFONE
        msg.text_body = 'localização'
        return msg

    def test_nao_envia_ultimo_recurso_em_modo_humano(self):
        svc = WebhookService()
        with patch.object(WebhookService, '_send_unified_interactive') as envio, \
             patch.object(WebhookService, '_mark_processed_by_agent'):
            enviou = svc._ultimo_recurso(self._evento(), self._msg_real(self.conversa))

        self.assertFalse(enviou)
        envio.assert_not_called()

    def test_continua_respondendo_quando_ninguem_assumiu(self):
        self.conversa.mode = Conversation.ConversationMode.AUTO
        self.conversa.save(update_fields=['mode'])
        svc = WebhookService()
        with patch.object(WebhookService, '_send_unified_interactive') as envio, \
             patch.object(WebhookService, '_mark_processed_by_agent'):
            enviou = svc._ultimo_recurso(self._evento(), self._msg_real(self.conversa))

        self.assertTrue(enviou)
        envio.assert_called_once()


class EcoDoAppAssumeAConversaTest(_Base):
    """O caso do Diogo: atender pelo app do Business é assumir a conversa."""

    def setUp(self):
        super().setUp()
        self.conversa.mode = Conversation.ConversationMode.AUTO
        self.conversa.save(update_fields=['mode'])
        self.patcher_broadcast = patch(
            'apps.whatsapp.services.broadcast_service.WhatsAppBroadcastService.broadcast_message_sent'
        )
        self.patcher_broadcast.start()
        self.addCleanup(self.patcher_broadcast.stop)

    def _eco(self, texto='Oiii', wamid='wamid.eco-1'):
        return {
            'id': wamid,
            'from': self.account.phone_number,
            'to': TELEFONE,
            'type': 'text',
            'text': {'body': texto},
        }

    def test_eco_do_lojista_passa_a_conversa_para_humano(self):
        WebhookService()._handle_message_echo(self.account, self._eco())

        self.conversa.refresh_from_db()
        self.assertEqual(
            self.conversa.mode, Conversation.ConversationMode.HUMAN,
            'o dono respondeu pelo app e o bot continuou solto na conversa',
        )

    def test_eco_grava_a_mensagem_no_inbox(self):
        WebhookService()._handle_message_echo(self.account, self._eco())
        self.assertTrue(
            Message.objects.filter(conversation=self.conversa, text_body='Oiii').exists()
        )

    def test_eco_ja_registrado_nao_reprocessa(self):
        Message.objects.create(
            account=self.account, conversation=self.conversa,
            whatsapp_message_id='wamid.eco-1', direction='outbound',
            message_type='text', status='sent',
            from_number=self.account.phone_number, to_number=TELEFONE,
            text_body='Oiii',
        )
        WebhookService()._handle_message_echo(self.account, self._eco())

        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.AUTO)

    def test_eco_do_proprio_bot_nao_silencia_o_bot(self):
        """Corrida: o eco pode chegar antes do wamid do envio ser gravado.

        Sem esta guarda, a primeira resposta do bot desligaria o bot para
        sempre naquela conversa.
        """
        Message.objects.create(
            account=self.account, conversation=self.conversa,
            whatsapp_message_id='', direction='outbound',
            message_type='text', status='sent',
            from_number=self.account.phone_number, to_number=TELEFONE,
            text_body='Como posso te ajudar? 👇',
            sent_at=timezone.now(),
        )
        WebhookService()._handle_message_echo(
            self.account, self._eco(texto='Como posso te ajudar? 👇', wamid='wamid.eco-bot'),
        )

        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.AUTO)

    def test_eco_chega_ao_inbox_de_verdade_sem_mock_do_broadcast(self):
        """Sem mock nenhum: o caminho real do eco não pode levantar.

        `_handle_message_echo` importava `BroadcastService` de um módulo que só
        define `WhatsAppBroadcastService`. O ImportError caía no `except` do
        próprio método, então cada eco virava um warning e ia embora: em 24h de
        11/ago foram 85 mensagens digitadas no celular pelo dono que nunca
        apareceram no inbox do painel. Um teste que mocka o broadcast não
        enxerga esse bug — este roda o caminho inteiro.
        """
        self.patcher_broadcast.stop()
        self.addCleanup(self.patcher_broadcast.start)

        with self.assertLogs('apps.whatsapp.services.webhook_service', level='WARNING') as capturado:
            logging.getLogger('apps.whatsapp.services.webhook_service').warning('marcador')
            WebhookService()._handle_message_echo(self.account, self._eco(wamid='wamid.eco-real'))

        self.assertNotIn(
            'Falha ao processar eco',
            '\n'.join(capturado.output),
            'o caminho real do eco levantou exceção',
        )
        self.assertTrue(
            Message.objects.filter(whatsapp_message_id='wamid.eco-real').exists(),
            'o eco tem que estar gravado no inbox',
        )

    def test_conversa_ja_humana_nao_muda_nada(self):
        self.conversa.mode = Conversation.ConversationMode.HUMAN
        self.conversa.save(update_fields=['mode'])
        WebhookService()._handle_message_echo(self.account, self._eco())

        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.HUMAN)
