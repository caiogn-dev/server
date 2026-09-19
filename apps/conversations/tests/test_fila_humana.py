"""A fila humana mostra quem está esperando uma pessoa — com dados reais.

Até 19/09 a página "Fila humana" do painel lia `HandoverRequest`, uma tabela
com ZERO linhas desde sempre: nada no sistema a preenchia quando o cliente
passava para atendimento humano. As passagens reais viviam em
`Conversation.mode` (331 conversas) e no histórico de handover (423 linhas).
O dono nunca viu a fila — e 7 clientes estavam esperando resposta.

A fila agora sai da conversa: modo humano + cliente escreveu depois da nossa
última resposta = esperando.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conversations.models import Conversation
from apps.conversations.services.atendimento_humano import assumir_atendimento
from apps.whatsapp.models import WhatsAppAccount

URL = '/api/v1/conversations/fila-humana/'


def _conta(dono, sufixo):
    return WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+55639000{sufixo}', display_phone_number=f'+55639000{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-fila', password='x')


@pytest.fixture
def conta(dono):
    return _conta(dono, '00011')


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(dono)
    return c


def _conversa(conta, tel, nome='Cliente', humana=True, cliente_escreveu=None,
              respondemos=None, origem='eco_do_app_business'):
    conv = Conversation.objects.create(account=conta, phone_number=tel, contact_name=nome)
    if humana:
        assumir_atendimento(conv, origem=origem)
    Conversation.objects.filter(pk=conv.pk).update(
        last_customer_message_at=cliente_escreveu, last_agent_message_at=respondemos,
    )
    return conv


@pytest.mark.django_db
class TestFilaHumana:
    def test_cliente_esperando_aparece_com_motivo_e_tempo(self, cliente, conta):
        agora = timezone.now()
        _conversa(conta, '5563999990101', nome='Joana',
                  cliente_escreveu=agora - timedelta(minutes=40),
                  respondemos=agora - timedelta(hours=2), origem='falha_da_ia')

        r = cliente.get(URL)

        assert r.status_code == 200, r.content
        esperando = r.json()['esperando']
        assert [e['nome'] for e in esperando] == ['Joana']
        assert 'IA' in esperando[0]['motivo']
        assert 38 <= esperando[0]['minutos_esperando'] <= 42

    def test_quem_espera_ha_mais_tempo_vem_primeiro(self, cliente, conta):
        agora = timezone.now()
        _conversa(conta, '5563999990102', nome='Recente', cliente_escreveu=agora - timedelta(minutes=5))
        _conversa(conta, '5563999990103', nome='Antiga', cliente_escreveu=agora - timedelta(hours=3))

        nomes = [e['nome'] for e in cliente.get(URL).json()['esperando']]

        assert nomes == ['Antiga', 'Recente']

    def test_respondido_depois_nao_esta_esperando(self, cliente, conta):
        agora = timezone.now()
        _conversa(conta, '5563999990104', nome='Atendida',
                  cliente_escreveu=agora - timedelta(minutes=30),
                  respondemos=agora - timedelta(minutes=10))

        corpo = cliente.get(URL).json()

        assert corpo['esperando'] == []
        assert [e['nome'] for e in corpo['em_atendimento']] == ['Atendida']

    def test_conversa_do_bot_nao_entra(self, cliente, conta):
        _conversa(conta, '5563999990105', humana=False,
                  cliente_escreveu=timezone.now() - timedelta(minutes=3))

        corpo = cliente.get(URL).json()

        assert corpo['esperando'] == [] and corpo['em_atendimento'] == []

    def test_humana_parada_de_outro_dia_nao_polui_a_fila(self, cliente, conta):
        """Sem cliente esperando e sem atendimento hoje: volta ao bot na próxima mensagem."""
        velha = timezone.now() - timedelta(days=3)
        conv = _conversa(conta, '5563999990106', cliente_escreveu=velha, respondemos=velha)
        from apps.handover.models import ConversationHandover
        ConversationHandover.objects.filter(conversation=conv).update(last_transfer_at=velha)

        corpo = cliente.get(URL).json()

        assert corpo['esperando'] == [] and corpo['em_atendimento'] == []

    def test_totais_para_o_contador_do_menu(self, cliente, conta):
        _conversa(conta, '5563999990107', cliente_escreveu=timezone.now())

        assert cliente.get(URL).json()['total_esperando'] == 1

    def test_conversa_de_outra_conta_nao_aparece(self, cliente, conta):
        outro = get_user_model().objects.create_user(username='outro-fila', password='x')
        _conversa(_conta(outro, '00099'), '5563999990108', nome='Alheia',
                  cliente_escreveu=timezone.now())

        assert cliente.get(URL).json()['esperando'] == []
