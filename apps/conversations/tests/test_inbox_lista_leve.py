"""A lista do inbox não pode agregar o histórico inteiro de mensagens da loja.

Relato do dono (02/nov/2026): "o chat do WhatsApp demora muito para abrir". O
log mostrou ~9 s em `GET /conversations/?page_size=30`, enquanto a `fila-humana`
da mesma tela levava cerca de 1 s.

`_accessible_conversations` contava mensagens com `Count('messages')`: um JOIN
com GROUP BY em todas as conversas da loja, antes do LIMIT da página. O `distinct()`
ainda impedia o Django de limpar a query de contagem da paginação, então a
agregação rodava duas vezes por requisição. O custo crescia com o histórico.
"""
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import Message, WhatsAppAccount

User = get_user_model()
URL = '/api/v1/conversations/?store=loja-leve&page=1&page_size=30'


def _mensagem(conta, conversa, ident, direcao='inbound', lida=False, texto='oi'):
    return Message(
        account=conta, conversation=conversa, whatsapp_message_id=f'wamid-{ident}',
        direction=direcao, message_type='text', from_number='1', to_number='2',
        text_body=texto, read_at=timezone.now() if lida else None,
    )


@pytest.fixture
def cenario(db):
    dono = User.objects.create_user(username='dono_leve', password='x')
    loja = Store.objects.create(owner=dono, name='Leve', slug='loja-leve')
    conta = WhatsAppAccount.objects.create(
        phone_number_id='pid-leve', waba_id='waba-leve',
        phone_number='+5563900000009', is_active=True, owner=dono,
    )
    conta.stores.add(loja)
    conversa = Conversation.objects.create(
        account=conta, phone_number='5563911110000', wa_id='5563911110000',
        contact_name='Com mensagens', is_active=True, last_message_at=timezone.now(),
    )
    vazia = Conversation.objects.create(
        account=conta, phone_number='5563911110001', wa_id='5563911110001',
        contact_name='Sem mensagens', is_active=True,
    )
    Message.objects.bulk_create([
        _mensagem(conta, conversa, 'a'),
        _mensagem(conta, conversa, 'b'),
        _mensagem(conta, conversa, 'c', lida=True),
        _mensagem(conta, conversa, 'd', direcao='outbound'),
    ])
    client = APIClient()
    client.force_authenticate(dono)
    return {'client': client, 'conversa': conversa, 'vazia': vazia}


def _queries_da_lista(cenario):
    with CaptureQueriesContext(connection) as ctx:
        resposta = cenario['client'].get(URL)
    assert resposta.status_code == 200, resposta.content
    return resposta, [q['sql'] for q in ctx.captured_queries]


def test_lista_nao_agrega_mensagens_com_group_by(cenario):
    _, queries = _queries_da_lista(cenario)
    com_group_by = [q for q in queries if 'GROUP BY' in q and 'LEFT OUTER JOIN "whatsapp_messages"' in q]
    assert not com_group_by, com_group_by[0][:600]


def test_contagem_da_paginacao_nao_toca_em_mensagens(cenario):
    _, queries = _queries_da_lista(cenario)
    contagens = [q for q in queries if q.startswith('SELECT COUNT(*)')]
    assert contagens, 'a paginação deveria contar as conversas'
    for q in contagens:
        assert 'whatsapp_messages' not in q, q[:600]


def test_contadores_continuam_certos(cenario):
    resposta, _ = _queries_da_lista(cenario)
    por_id = {str(c['id']): c for c in resposta.data['results']}

    com = por_id[str(cenario['conversa'].id)]
    assert com['message_count'] == 4
    assert com['unread_count'] == 2  # inbound sem read_at

    # Sem mensagem é 0, não None: o serializer cairia em query por linha.
    vazia = por_id[str(cenario['vazia'].id)]
    assert vazia['message_count'] == 0
    assert vazia['unread_count'] == 0


def test_conta_ligada_a_loja_nas_duas_formas_nao_duplica_conversa(cenario):
    resposta, _ = _queries_da_lista(cenario)
    ids = [c['id'] for c in resposta.data['results']]
    assert len(ids) == len(set(ids))
    assert resposta.data['count'] == 2
