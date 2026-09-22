"""O dono vê o que a loja mandou sozinha: o quê, para quem, quando, se chegou.

19/09: as mensagens automáticas passaram a ser gravadas, mas o painel não
tinha onde mostrá-las — a tela "Mensagens automáticas" só edita os textos.
O histórico sai de `whatsapp_messages`: marca `automatico` (a partir de 19/09)
ou a `source` que status e avaliação já gravavam antes disso.
"""
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount

URL = '/api/v1/conversations/mensagens-automaticas/'


def _conta(dono, sufixo):
    return WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+55639000{sufixo}', display_phone_number=f'+55639000{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )


def _msg(conta, conversa, texto, metadata, status='sent', quando=None, direction='outbound'):
    m = Message.objects.create(
        account=conta, conversation=conversa, whatsapp_message_id=f'wamid.{uuid.uuid4().hex}',
        direction=direction, message_type='text', status=status,
        from_number=conta.phone_number, to_number=conversa.phone_number,
        text_body=texto, metadata=metadata, error_message='número inválido' if status == 'failed' else '',
    )
    if quando:
        Message.objects.filter(pk=m.pk).update(created_at=quando)
    return m


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-historico', password='x')


@pytest.fixture
def conta(dono):
    return _conta(dono, '00031')


@pytest.fixture
def conversa(conta):
    return Conversation.objects.create(account=conta, phone_number='5563999991001', contact_name='Marta')


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(dono)
    return c


@pytest.mark.django_db
class TestHistoricoDeAutomaticas:

    def test_lista_so_as_automaticas_com_rotulo_e_cliente(self, cliente, conta, conversa):
        _msg(conta, conversa, 'Seu PIX está esperando', {'automatico': True, 'evento': 'pix_reminder'})
        _msg(conta, conversa, 'Resposta do atendente', {'source': 'whatsapp_inbox_page'})
        _msg(conta, conversa, 'Oi', {}, direction='inbound')

        r = cliente.get(URL)

        assert r.status_code == 200, r.content
        itens = r.json()['itens']
        assert [i['texto'] for i in itens] == ['Seu PIX está esperando']
        assert itens[0]['rotulo'] == 'Lembrete de PIX'
        assert itens[0]['cliente'] == 'Marta'
        assert itens[0]['conversa_id'] == str(conversa.id)

    def test_status_e_avaliacao_de_antes_da_marca_tambem_aparecem(self, cliente, conta, conversa):
        _msg(conta, conversa, 'Saiu para entrega', {'source': 'order_status_notification', 'status': 'out_for_delivery'})
        _msg(conta, conversa, 'Avalie', {'source': 'feedback_request'})
        _msg(conta, conversa, 'Pronto', {'source': 'store_order_notification'})

        rotulos = {i['rotulo'] for i in cliente.get(URL).json()['itens']}

        assert rotulos == {'Status do pedido', 'Pedido de avaliação'}

    def test_resumo_conta_enviadas_e_falhas_por_tipo(self, cliente, conta, conversa):
        _msg(conta, conversa, 'a', {'automatico': True, 'evento': 'order_delivered'})
        _msg(conta, conversa, 'b', {'automatico': True, 'evento': 'order_ready'}, status='delivered')
        _msg(conta, conversa, 'c', {'automatico': True, 'evento': 'order_ready'}, status='failed')

        resumo = {r['tipo']: r for r in cliente.get(URL).json()['resumo']}

        assert resumo['status']['total'] == 3
        assert resumo['status']['falharam'] == 1
        assert resumo['status']['rotulo'] == 'Status do pedido'

    def test_falha_traz_o_motivo(self, cliente, conta, conversa):
        _msg(conta, conversa, 'x', {'automatico': True, 'evento': 'cart_reminder'}, status='failed')

        item = cliente.get(URL).json()['itens'][0]

        assert item['status'] == 'failed'
        assert item['erro'] == 'número inválido'

    def test_filtra_por_tipo_e_periodo(self, cliente, conta, conversa):
        _msg(conta, conversa, 'novo', {'automatico': True, 'evento': 'reengagement'})
        _msg(conta, conversa, 'velho', {'automatico': True, 'evento': 'reengagement'},
             quando=timezone.now() - timedelta(days=10))
        _msg(conta, conversa, 'pix', {'automatico': True, 'evento': 'pix_reminder'})

        r = cliente.get(URL, {'tipo': 'reengagement', 'dias': 7}).json()

        assert [i['texto'] for i in r['itens']] == ['novo']

    def test_dono_nao_ve_as_de_outra_loja(self, cliente, db):
        outro = get_user_model().objects.create_user(username='outro-historico', password='x')
        conta_alheia = _conta(outro, '00032')
        conv = Conversation.objects.create(account=conta_alheia, phone_number='5563999991002')
        _msg(conta_alheia, conv, 'alheia', {'automatico': True, 'evento': 'pix_reminder'})

        r = cliente.get(URL).json()

        assert r['itens'] == []
        assert r['resumo'] == []

    def test_exige_login(self, db):
        assert APIClient().get(URL).status_code in (401, 403)

    def test_falha_da_janela_de_24h_vem_explicada(self, cliente, conta, conversa):
        m = _msg(conta, conversa, 'x', {'automatico': True, 'evento': 'order_ready'}, status='failed')
        Message.objects.filter(pk=m.pk).update(error_code='131047', error_message='Re-engagement message')

        item = cliente.get(URL).json()['itens'][0]

        assert '24 h' in item['erro']
        assert item['erro_tecnico'] == '131047 · Re-engagement message'
