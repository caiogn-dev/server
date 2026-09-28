"""Conversão do bot: quantas conversas viram pedido, e onde a venda para.

Medido em 28/09 na Cê Saladas (30 dias): 186 conversas, 10 pedidos pelo
WhatsApp, 144 transferências para atendente, 16 carrinhos parados. Nenhum
desses números existia como tela — cada agente novo seria opinião.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automation.models import CompanyProfile, CustomerSession, IntentLog
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import Message, WhatsAppAccount

BASE = '/api/v1/conversations'


def _loja(dono, sufixo):
    loja = Store.objects.create(name=f'Loja {sufixo}', slug=f'loja-{sufixo}', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+5563900{sufixo}', display_phone_number=f'+5563900{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    return loja, conta


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-cv', password='x')


@pytest.fixture
def loja_e_conta(dono):
    return _loja(dono, '00031')


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(dono)
    return c


def _conversa(conta, tel, nome='', texto='oi', ha_minutos=10, modo='auto'):
    conv = Conversation.objects.create(account=conta, phone_number=tel, contact_name=nome, mode=modo)
    quando = timezone.now() - timedelta(minutes=ha_minutos)
    Message.objects.create(
        account=conta, conversation=conv, whatsapp_message_id=f'in-{tel}-{ha_minutos}', direction='inbound',
        message_type='text', from_number=tel, to_number=conta.phone_number, text_body=texto,
    )
    Conversation.objects.filter(pk=conv.pk).update(last_customer_message_at=quando, last_message_at=quando)
    Message.objects.filter(conversation=conv).update(created_at=quando)
    return conv


def _pedido(loja, tel, total='50.00', source='whatsapp', pago=True):
    return StoreOrder.objects.create(
        store=loja, customer_phone=tel, customer_name='X', source=source, subtotal=Decimal(total),
        total=Decimal(total), payment_status='paid' if pago else 'pending', status='confirmed',
    )


@pytest.mark.django_db
class TestConversaoDoBot:
    def test_funil_e_motivos(self, cliente, loja_e_conta):
        loja, conta = loja_e_conta
        perfil = CompanyProfile.objects.get(store=loja)
        # 1) virou pedido
        _conversa(conta, '5563999990401', 'Ana', 'quero 2 saladas')
        _pedido(loja, '5563999990401', '60.00')
        # 2) foi para atendente
        conv2 = _conversa(conta, '5563999990402', 'Bia', 'falar com alguém')
        from apps.conversations.services import ConversationService
        ConversationService().switch_to_human(str(conv2.id), motivo='A IA não conseguiu responder')
        # 3) carrinho parado
        _conversa(conta, '5563999990403', 'Ca', '1 frango')
        CustomerSession.objects.create(company=perfil, phone_number='5563999990403', status='active',
                                       cart_items_count=1, cart_total=Decimal('30'))
        # 4) bot falhou
        _conversa(conta, '5563999990404', 'Du', 'cade vc')
        IntentLog.objects.create(company=perfil, phone_number='5563999990404', message_text='cade vc',
                                 intent_type='unknown', response_text='Desculpa, tive um probleminha aqui.')
        # 5) só perguntou
        _conversa(conta, '5563999990405', 'Ed', 'vcs abrem domingo?')
        # fora da janela
        _conversa(conta, '5563999990406', 'Fa', 'velha', ha_minutos=60 * 24 * 40)
        # pedido do site não conta como conversão do bot
        _pedido(loja, '5563999990405', '80.00', source='web')

        r = cliente.get(f'{BASE}/bot/conversao/?store={loja.slug}&dias=30')

        assert r.status_code == 200, r.content
        d = r.json()
        assert d['conversas'] == 5
        assert d['pedidos'] == 1
        assert d['receita'] == '60.00'
        assert d['taxa'] == 20.0
        assert d['para_atendente'] == 1
        assert d['carrinho_parado'] == 1
        assert d['bot_falhou'] == 1
        assert d['motivos_de_atendente'] == [{'motivo': 'A IA não conseguiu responder', 'vezes': 1}]
        assert len(d['serie']) == 30 and sum(p['conversas'] for p in d['serie']) == 5
        perdidas = {p['telefone']: p for p in d['perdidas']}
        assert set(perdidas) == {'5563999990402', '5563999990403', '5563999990404', '5563999990405'}
        assert perdidas['5563999990402']['motivo'] == 'atendente'
        assert perdidas['5563999990403']['motivo'] == 'carrinho'
        assert perdidas['5563999990404']['motivo'] == 'bot_falhou'
        assert perdidas['5563999990405']['motivo'] == 'so_perguntou'
        assert perdidas['5563999990405']['ultima_mensagem'] == 'vcs abrem domingo?'
        assert perdidas['5563999990405']['nome'] == 'Ed'

    def test_loja_alheia_e_404_e_sem_store_soma_as_do_usuario(self, cliente, loja_e_conta, db):
        loja, conta = loja_e_conta
        _conversa(conta, '5563999990411')
        outro = get_user_model().objects.create_user(username='outro-cv', password='x')
        outra, outra_conta = _loja(outro, '00032')
        _conversa(outra_conta, '5563999990412')

        assert cliente.get(f'{BASE}/bot/conversao/?store={outra.slug}').status_code == 404
        assert cliente.get(f'{BASE}/bot/conversao/').json()['conversas'] == 1

    def test_sem_conversa_taxa_e_zero_nao_erro(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        d = cliente.get(f'{BASE}/bot/conversao/?store={loja.slug}').json()
        assert d['conversas'] == 0 and d['taxa'] == 0 and d['perdidas'] == []
