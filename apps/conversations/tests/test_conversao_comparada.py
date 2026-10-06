"""A tela de Conversão compara com o período anterior e marca os ensinos.

Pergunta do dono (06/10): "como vemos a evolução? como vemos mudança?". A
série por dia existia, mas não dava para ler "esta semana × a passada" nem
saber se um ensino mudou alguma coisa.
"""
import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.agents.models import Agent, AgentKnowledgeEntry
from apps.conversations.models import Conversation
from apps.conversations.services.conversao_do_bot import funil
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import Message, WhatsAppAccount

_ids = itertools.count()


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-cmp', password='x')
    loja = Store.objects.create(name='Cê Cmp', slug='ce-cmp', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(name='Cmp', phone_number_id='PHCMP', waba_id='WCMP')
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    return loja


def _conversa(loja, telefone, dias_atras, pediu=False):
    quando = timezone.now() - timedelta(days=dias_atras, hours=1)
    conv = Conversation.objects.create(account_id=loja.whatsapp_account_id, phone_number=telefone,
                                       last_customer_message_at=quando)
    m = Message.objects.create(
        account_id=loja.whatsapp_account_id, conversation=conv, whatsapp_message_id=f'wamid.cmp{next(_ids)}',
        direction='inbound', message_type='text', from_number=telefone, to_number='loja', text_body='oi',
    )
    Message.objects.filter(pk=m.pk).update(created_at=quando)
    if pediu:
        o = StoreOrder.objects.create(store=loja, customer_phone=telefone, customer_name='C', source='whatsapp',
                                      subtotal=Decimal('30'), total=Decimal('30'))
        StoreOrder.objects.filter(pk=o.pk).update(created_at=quando)


@pytest.mark.django_db
def test_compara_com_a_semana_anterior(loja):
    # semana atual: 4 conversas, 2 pedidos
    for i in range(4):
        _conversa(loja, f'556399000{i:04d}', dias_atras=2, pediu=i < 2)
    # semana anterior: 5 conversas, 1 pedido
    for i in range(5):
        _conversa(loja, f'556398000{i:04d}', dias_atras=9, pediu=i < 1)

    cmp = funil([loja], dias=7)['comparativo']

    assert (cmp['atual']['conversas'], cmp['atual']['pedidos'], cmp['atual']['taxa']) == (4, 2, 50.0)
    assert (cmp['anterior']['conversas'], cmp['anterior']['pedidos'], cmp['anterior']['taxa']) == (5, 1, 20.0)


@pytest.mark.django_db
def test_marcos_mostram_o_que_foi_ensinado_no_periodo(loja):
    agente = Agent.objects.create(name='IA Cmp', provider=Agent.AgentProvider.NVIDIA)
    AgentKnowledgeEntry.objects.create(agent=agente, store=loja, topic='entrega', source='reviewed',
                                       example_input='entregam no sul?', example_response='Sim.')
    AgentKnowledgeEntry.objects.create(agent=agente, store=loja, topic='entrega', source='sugestao',
                                       example_input='não aprovado', example_response='x')

    marcos = funil([loja], dias=7)['marcos']

    assert [m['texto'] for m in marcos] == ['entregam no sul?']
    assert marcos[0]['tipo'] == 'ensino'
