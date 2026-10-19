"""Resposta do bot que fica pronta DEPOIS de o atendente assumir não sai.

19/10/2026, conversa da Mavi:

    15:51:04,2  cliente   "eu já pedi"            → bot começa a pensar
    15:51:04,5  atendente "Oiii, 10 minutinhos…"  → conversa vira humano
    15:51:13    atendente "Acabei de verificar o seu pedido"
    15:51:21    atendente "Já foi enviado para a produção!"
    15:51:44    BOT       "Ah, entendi! Você já tem um pedido feito? …"

O modo humano era checado na ENTRADA da mensagem — quando ainda era bot. O
LLM levou 40 s; nesse tempo a atendente resolveu, e a resposta velha saiu
por cima dela. A checagem tem que se repetir na SAÍDA, no gargalo por onde
toda resposta automática passa.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.conversations.models import Conversation
from apps.handover.models import ConversationHandover
from apps.whatsapp import tasks
from apps.whatsapp.models import Message, WhatsAppAccount


@pytest.fixture
def conversa(db):
    dono = get_user_model().objects.create_user(username='dono-atropelo', password='x')
    conta = WhatsAppAccount.objects.create(
        name='Conta Atropelo', phone_number_id='pn-atropelo', waba_id='wa-atropelo',
        phone_number='+5563900000071', display_phone_number='+5563900000071',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )
    return Conversation.objects.create(account=conta, phone_number='5563981039494')


def _entrada(conversa, wamid='wamid.eu-ja-pedi'):
    return Message.objects.create(
        account=conversa.account, conversation=conversa, whatsapp_message_id=wamid,
        direction='inbound', message_type='text', from_number='556381039494',
        to_number='5563900000071', text_body='eu já pedi',
    )


def _virar_humano(conversa, quando):
    Conversation.objects.filter(pk=conversa.pk).update(mode=Conversation.ConversationMode.HUMAN)
    ConversationHandover.objects.update_or_create(
        conversation=conversa, defaults={'status': 'human', 'last_transfer_at': quando},
    )


def _responder(conversa, reply_to, source='unified_llm'):
    with patch('apps.whatsapp.services.MessageService') as servico:
        tasks.send_agent_response(
            account_id=str(conversa.account_id),
            to='556381039494',
            response_text='Ah, entendi! Você já tem um pedido feito?',
            reply_to=reply_to,
            response_source=source,
        )
    return servico.return_value.send_text_message.called


@pytest.mark.django_db
def test_atendente_assumiu_enquanto_o_bot_pensava_resposta_nao_sai(conversa):
    entrada = _entrada(conversa)
    _virar_humano(conversa, entrada.created_at + timedelta(milliseconds=300))

    assert not _responder(conversa, entrada.whatsapp_message_id)


@pytest.mark.django_db
def test_conversa_ja_era_humana_antes_resposta_liberada_sai(conversa):
    """Se a conversa já era humana quando a mensagem chegou, quem deixou o bot
    responder foi a triagem da entrada (clique em botão do próprio bot,
    localização com checkout esperando). Esse caminho segue liberado."""
    _virar_humano(conversa, timezone.now() - timedelta(minutes=5))
    entrada = _entrada(conversa)

    assert _responder(conversa, entrada.whatsapp_message_id)


@pytest.mark.django_db
def test_conversa_no_bot_resposta_sai(conversa):
    entrada = _entrada(conversa)

    assert _responder(conversa, entrada.whatsapp_message_id)
