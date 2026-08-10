"""Modo humano: as duas camadas precisam concordar sobre o que é fluxo do bot.

10/ago/2026, ao vivo com a Dyana: ela recebeu o convite de avaliação, clicou
⭐⭐⭐⭐⭐ e recebeu de volta "Recebi sua mensagem, mas não consegui responder
direito agora 😕". O link do Google nunca foi enviado.

A causa foi DUAS listas para a mesma decisão, que divergiram:

- `webhook_service._should_suppress_for_human_mode` liberava
  ('add_', 'product_', 'rating_', 'review_done_', 'refer_friend_', 'track_');
- `unified_service._is_human_mode_transactional_step` — a camada que de fato
  responde — só conhecia ('add_', 'product_') e os ids de checkout.

Resultado: o webhook deixava passar, logava "Human mode bypass for
deterministic order flow", e o orquestrador engolia em silêncio. Nenhum caminho
respondia, e o cliente levava a mensagem de último recurso.

Contrato: uma fonte única (`apps.automation.services.fluxos_do_bot`) e paridade
verificada aqui, para que acrescentar um botão novo em um lado não volte a
deixar o outro para trás.
"""
from django.test import TestCase

from apps.automation.services.fluxos_do_bot import (
    IDS_TRANSACIONAIS, PREFIXOS_DE_FLUXO_DO_BOT, eh_fluxo_do_bot,
)
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService


def _reply(reply_id):
    return {'type': 'button_reply', 'id': reply_id, 'title': '...'}


class _MensagemFalsa:
    def __init__(self, conversation):
        self.id = 'msg-1'
        self.conversation = conversation


class FluxoDoBotTest(TestCase):
    """A fonte única em si."""

    def test_clique_de_avaliacao_e_fluxo_do_bot(self):
        self.assertTrue(eh_fluxo_do_bot('rating_5_abc-123'))

    def test_ids_de_checkout_sao_fluxo_do_bot(self):
        for reply_id in IDS_TRANSACIONAIS:
            self.assertTrue(eh_fluxo_do_bot(reply_id), reply_id)

    def test_botao_desconhecido_nao_e_fluxo_do_bot(self):
        """O bypass não pode virar porta aberta: no modo humano o padrão é calar."""
        self.assertFalse(eh_fluxo_do_bot('montar_salada'))
        self.assertFalse(eh_fluxo_do_bot(''))
        self.assertFalse(eh_fluxo_do_bot(None))


class ParidadeEntreAsCamadasTest(TestCase):
    """O webhook e o orquestrador não podem discordar."""

    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_PAR', waba_id='WABA_PAR',
        )
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563984143551', mode='human',
        )

    def _webhook_libera(self, reply_id) -> bool:
        suprime = WebhookService()._should_suppress_for_human_mode(
            _MensagemFalsa(self.conversation), _reply(reply_id), None,
        )
        return not suprime

    def _orquestrador_libera(self, reply_id) -> bool:
        service = UnifiedService(self.account, self.conversation, use_llm=False)
        return service._is_human_mode_transactional_step('', _reply(reply_id), None)

    def test_avaliacao_5_estrelas_passa_nas_duas_camadas(self):
        """O caso da Dyana. Antes: webhook True, orquestrador False."""
        reply_id = 'rating_5_d1d8e6d0-5b45-4769-a307-4a60d34e2caf'
        self.assertTrue(self._webhook_libera(reply_id))
        self.assertTrue(self._orquestrador_libera(reply_id))

    def test_todo_prefixo_liberado_no_webhook_passa_no_orquestrador(self):
        """Paridade completa: deixar passar e não responder é pior que calar."""
        for prefixo in PREFIXOS_DE_FLUXO_DO_BOT:
            reply_id = f'{prefixo}exemplo-123'
            self.assertTrue(self._webhook_libera(reply_id), prefixo)
            self.assertTrue(self._orquestrador_libera(reply_id), prefixo)

    def test_todo_id_transacional_passa_nas_duas_camadas(self):
        for reply_id in IDS_TRANSACIONAIS:
            self.assertTrue(self._webhook_libera(reply_id), reply_id)
            self.assertTrue(self._orquestrador_libera(reply_id), reply_id)

    def test_botao_fora_dos_fluxos_continua_suprimido_nas_duas(self):
        """Atendente humano no comando não pode ser atropelado pelo bot."""
        self.assertFalse(self._webhook_libera('montar_salada'))
        self.assertFalse(self._orquestrador_libera('montar_salada'))

    def test_conversa_fora_do_modo_humano_nao_e_suprimida(self):
        self.conversation.mode = 'bot'
        self.conversation.save(update_fields=['mode'])
        self.assertTrue(self._webhook_libera('montar_salada'))
