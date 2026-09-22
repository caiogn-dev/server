"""As três decisões do dono sobre quando a loja fala sozinha (21/09/2026).

1. **Modo humano cala tudo.** Enquanto um atendente está na conversa, nenhuma
   mensagem automática sai — nem status de pedido. Elas voltam quando a
   conversa volta para o bot. (Decisão do dono; a consequência é que quem está
   falando com o atendente não recebe "saiu para entrega" naquele momento.)
2. **Silenciar o pedido vale para TODOS os status — e só para status.** O
   convite de avaliação continua saindo.
3. Lembrete de carrinho e de PIX não olham a lista de "parar promoções": são
   transacionais, o cliente está no meio de uma compra.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.mensageiro import politica
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount


@pytest.fixture
def conta(db):
    return WhatsAppAccount.objects.create(
        name='Loja', phone_number_id='PH-POL', waba_id='WABA-POL',
    )


def _conversa(conta, telefone, modo):
    return Conversation.objects.create(
        account=conta, phone_number=telefone, mode=modo,
        last_customer_message_at=timezone.now(),
    )


class TestModoHumano:
    def test_conversa_com_atendente_cala_a_automatica(self, conta):
        _conversa(conta, '5563911110001', Conversation.ConversationMode.HUMAN)

        assert politica.silenciado(conta, '5563911110001') is True

    def test_conversa_no_bot_deixa_falar(self, conta):
        _conversa(conta, '5563911110002', Conversation.ConversationMode.AUTO)

        assert politica.silenciado(conta, '5563911110002') is False

    def test_sem_conversa_nenhuma_deixa_falar(self, conta):
        assert politica.silenciado(conta, '5563911110003') is False

    def test_numero_em_outro_formato_tambem_e_reconhecido(self, conta):
        _conversa(conta, '5563911110004', Conversation.ConversationMode.HUMAN)

        assert politica.silenciado(conta, '63911110004') is True


@pytest.mark.django_db
def test_canal_nao_envia_em_modo_humano(conta):
    from apps.automation.mensageiro import canal

    _conversa(conta, '5563911110005', Conversation.ConversationMode.HUMAN)
    servico = MagicMock()

    with patch('apps.whatsapp.services.message_service.MessageService', return_value=servico):
        resultado = canal.enviar_texto(conta, '5563911110005', 'oi', evento='order_preparing')

    assert resultado is None
    servico.send_text_message.assert_not_called()


@pytest.mark.django_db
def test_canal_envia_normalmente_no_bot(conta):
    from apps.automation.mensageiro import canal
    from apps.whatsapp.models import Message

    _conversa(conta, '5563911110006', Conversation.ConversationMode.AUTO)
    servico = MagicMock()
    servico.send_text_message.return_value = MagicMock(status=Message.MessageStatus.SENT)

    with patch('apps.whatsapp.services.message_service.MessageService', return_value=servico):
        canal.enviar_texto(conta, '5563911110006', 'oi', evento='order_preparing')

    servico.send_text_message.assert_called_once()
