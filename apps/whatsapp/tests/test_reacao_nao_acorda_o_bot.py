"""Reação (emoji) não é pergunta — o bot não responde a ela.

21/09/2026, conversa 5563981411267: o cliente reagiu a uma mensagem com um
emoji e o bot respondeu "Desculpa, tive um probleminha aqui. Pode repetir?".

A reação virava `text_body = '🇮🇱'` e entrava no pipeline como se a pessoa
tivesse digitado aquilo. Nenhum handler entende um emoji solto, então a
conversa caía no fallback de erro — e o cliente lê "tive um problema" depois
de só ter tocado num coraçãozinho.

Reação é META-interação: comenta uma mensagem, não pede nada. Igual ao áudio
sem transcrição, que o pipeline já ignora de propósito: silêncio é melhor que
"não entendi".
"""
import pytest
from django.contrib.auth import get_user_model

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import Message, WhatsAppAccount

TELEFONE = '5563981411267'


@pytest.fixture
def cenario(db):
    dono = get_user_model().objects.create_user(username='dono-reacao', password='x')
    loja = Store.objects.create(name='Loja', slug='loja-reacao', owner=dono, billing_exempt=True)
    conta = WhatsAppAccount.objects.create(name='C', phone_number_id='PH-RE', waba_id='WA-RE')
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    perfil = CompanyProfile.objects.get(store=loja)
    # O signal de criação da loja já liga um perfil à conta; limpar os outros
    # evita a colisão do índice único no banco de teste compartilhado.
    CompanyProfile.objects.filter(account=conta).exclude(pk=perfil.pk).delete()
    perfil.account = conta
    perfil.save()
    conversa = Conversation.objects.create(account=conta, phone_number=TELEFONE)
    return conta, conversa


def _mensagem(conta, conversa, tipo, texto):
    return Message.objects.create(
        account=conta, conversation=conversa, direction='inbound',
        message_type=tipo, content={'text': texto}, text_body=texto,
        from_number=TELEFONE,
    )


def test_reacao_nao_entra_no_pipeline(cenario):
    from unittest.mock import MagicMock, patch

    from apps.whatsapp.services.webhook_service import WebhookService

    conta, conversa = cenario
    reacao = _mensagem(conta, conversa, Message.MessageType.REACTION, '❤️')
    evento = MagicMock(account=conta, payload={'message': {'type': 'reaction'}})

    servico = WebhookService()
    with patch.object(servico, '_tratar_pedido_de_saida') as saida:
        servico.post_process_inbound_message(evento, reacao)

    # Nem chegou ao primeiro passo do pipeline.
    saida.assert_not_called()


def test_texto_normal_continua_entrando(cenario):
    from unittest.mock import MagicMock, patch

    from apps.whatsapp.services.webhook_service import WebhookService

    conta, conversa = cenario
    texto = _mensagem(conta, conversa, Message.MessageType.TEXT, 'oi, tem salada?')
    evento = MagicMock(account=conta, payload={'message': {'type': 'text'}})

    servico = WebhookService()
    with patch.object(servico, '_tratar_pedido_de_saida', return_value=True) as saida:
        servico.post_process_inbound_message(evento, texto)

    saida.assert_called_once()
