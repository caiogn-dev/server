"""14/10 — a Enna mandou três mensagens em 23 segundos e recebeu respostas que
se contradiziam.

    12:41:57  sim sim
    12:42:02  passa o pix por favor
    12:42:20  vou ter que comer correndo rs
    12:42:38  BOT  (resposta ao "sim sim")       Confirma o endereço?
    12:42:39  BOT  (resposta ao "comer correndo") Confirmo o endereço? …
    12:43:28  BOT  (resposta ao "passa o pix")    Pedido confirmado + PIX
    12:43:28  BOT  (o "isso" dela caiu no atalho de "sim") PIX de novo

A trava por conversa já existia, mas cada mensagem ganhava a SUA resposta da
IA (11 a 49 s cada) e a trava não é fila: o "passa o pix" esperou e foi o
último. Agora a rajada vira UMA resposta: a mensagem que já tem outra mais
nova atrás não responde, e a mais nova lê o texto de todas.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService

TELEFONE = '5563992129009'


@pytest.fixture
def cenario(db):
    cache.clear()
    dono = get_user_model().objects.create_user(username='dono-rajada', password='x')
    loja = Store.objects.create(name='Loja', slug='loja-rajada', owner=dono, billing_exempt=True)
    conta = WhatsAppAccount.objects.create(name='C', phone_number_id='PH-RJ', waba_id='WA-RJ')
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    perfil = CompanyProfile.objects.get(store=loja)
    CompanyProfile.objects.filter(account=conta).exclude(pk=perfil.pk).delete()
    conversa = Conversation.objects.create(account=conta, phone_number=TELEFONE)
    return conta, conversa


def _msg(conta, conversa, texto, tipo='text'):
    return Message.objects.create(
        account=conta, conversation=conversa, direction='inbound',
        message_type=tipo, content={'text': texto}, text_body=texto, from_number=TELEFONE,
        whatsapp_message_id=f'wamid.{uuid.uuid4().hex}',
    )


def test_mensagem_com_outra_mais_nova_atras_nao_responde(cenario):
    conta, conversa = cenario
    sim = _msg(conta, conversa, 'sim sim')
    pix = _msg(conta, conversa, 'passa o pix por favor')
    svc = WebhookService()
    assert svc._mensagem_superada(sim) is True
    assert svc._mensagem_superada(pix) is False


def test_a_mais_nova_le_a_rajada_inteira_em_ordem(cenario):
    conta, conversa = cenario
    anterior = _msg(conta, conversa, 'quero uma de camarão')
    svc = WebhookService()
    svc._marcar_processada(anterior)
    _msg(conta, conversa, 'sim sim')
    _msg(conta, conversa, 'passa o pix por favor')
    ultima = _msg(conta, conversa, 'vou ter que comer correndo rs')
    assert svc._texto_da_rajada(ultima) == 'sim sim\npassa o pix por favor\nvou ter que comer correndo rs'


def test_depois_de_processar_a_proxima_le_so_o_que_e_dela(cenario):
    conta, conversa = cenario
    svc = WebhookService()
    svc._marcar_processada(_msg(conta, conversa, 'passa o pix por favor'))
    isso = _msg(conta, conversa, 'isso')
    assert svc._texto_da_rajada(isso) == 'isso'


def test_sem_marca_de_processada_le_so_a_propria(cenario):
    """Sem saber o que já foi respondido, não arrisca repetir conversa velha."""
    conta, conversa = cenario
    _msg(conta, conversa, 'oie')
    agora = _msg(conta, conversa, 'da tempo de pedir?')
    assert WebhookService()._texto_da_rajada(agora) == 'da tempo de pedir?'


def test_figurinha_mais_nova_nao_cala_a_mensagem_de_texto(cenario):
    """Sticker e reação não são processados — o texto antes deles ficaria sem resposta."""
    conta, conversa = cenario
    pedido = _msg(conta, conversa, 'passa o pix por favor')
    _msg(conta, conversa, '', tipo='sticker')
    assert WebhookService()._mensagem_superada(pedido) is False


def test_clique_em_botao_nunca_e_agrupado(cenario):
    """Botão é decisão explícita (forma de pagamento, confirmar) — responde sempre."""
    conta, conversa = cenario
    botao = _msg(conta, conversa, 'PIX', tipo='interactive')
    _msg(conta, conversa, 'rapido por favor')
    assert WebhookService()._mensagem_superada(botao) is False
