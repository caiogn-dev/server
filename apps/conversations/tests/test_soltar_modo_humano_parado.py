"""Soltar as conversas presas em modo humano antes da regra do dia seguinte.

19/09: 331 conversas em modo humano; 263 paradas há mais de 24h sem ninguém
esperando. Decisão do dono: essas voltam ao bot; quem tem cliente esperando
fica (aparece na fila). Prévia por padrão; só grava com --aplicar.
"""
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.conversations.models import Conversation
from apps.conversations.services.atendimento_humano import assumir_atendimento
from apps.handover.models import ConversationHandover
from apps.whatsapp.models import WhatsAppAccount

HUMANO = Conversation.ConversationMode.HUMAN
BOT = Conversation.ConversationMode.AUTO


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-soltar', password='x')
    return WhatsAppAccount.objects.create(
        name='Conta Soltar', phone_number_id='pn-soltar', waba_id='wa-soltar',
        phone_number='+5563900000077', display_phone_number='+5563900000077',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


def _humana(conta, tel, ultima_humana, cliente_escreveu=None):
    conv = Conversation.objects.create(account=conta, phone_number=tel, contact_name='C')
    assumir_atendimento(conv, origem='eco_do_app_business')
    ConversationHandover.objects.filter(conversation=conv).update(last_transfer_at=ultima_humana)
    Conversation.objects.filter(pk=conv.pk).update(
        last_agent_message_at=ultima_humana, last_customer_message_at=cliente_escreveu,
    )
    return conv


def _modo(conv):
    conv.refresh_from_db()
    return conv.mode


@pytest.mark.django_db
class TestSoltarModoHumanoParado:
    def test_previa_nao_muda_nada(self, conta):
        parada = _humana(conta, '5563999990201', timezone.now() - timedelta(days=5))
        saida = StringIO()

        call_command('soltar_modo_humano_parado', stdout=saida)

        assert _modo(parada) == HUMANO
        assert '1' in saida.getvalue()

    def test_aplicar_solta_a_parada_ha_mais_de_24h(self, conta):
        parada = _humana(conta, '5563999990202', timezone.now() - timedelta(days=5))

        call_command('soltar_modo_humano_parado', '--aplicar', stdout=StringIO())

        assert _modo(parada) == BOT

    def test_cliente_esperando_fica_humano(self, conta):
        velha = timezone.now() - timedelta(days=5)
        esperando = _humana(conta, '5563999990203', velha,
                            cliente_escreveu=velha + timedelta(hours=1))

        call_command('soltar_modo_humano_parado', '--aplicar', stdout=StringIO())

        assert _modo(esperando) == HUMANO

    def test_atendimento_das_ultimas_24h_fica(self, conta):
        recente = _humana(conta, '5563999990204', timezone.now() - timedelta(hours=3))

        call_command('soltar_modo_humano_parado', '--aplicar', stdout=StringIO())

        assert _modo(recente) == HUMANO
