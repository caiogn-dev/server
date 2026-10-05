"""Aviso de status COM texto da loja configurado também sai pelo modelo fora da janela.

Medido em 02/10/2026 (14 dias, Cê Saladas): 324 avisos de status tentados,
ZERO pelo modelo `aviso_de_pedido` — aprovado na conta desde 25/09 — e 76
falharam com 131047 (30 de 92 "confirmado", 9 de 60 "saiu para entrega").

Causa: o modelo mora no canal (`mensageiro.enviar_texto`), mas a tarefa
`notify_order_status_change` só passava pelo canal no caminho de RESERVA (loja
sem AutoMessage). Cê Saladas e Pastita têm AutoMessage para todos os status,
então todo aviso ia por `MessageService.send_text_message` direto: sem
modelo, sem janela, sem modo humano.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.mensageiro import modelo
from apps.automation.models import AutoMessage, CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import Message, MessageTemplate, WhatsAppAccount
from apps.whatsapp.tasks import automation_tasks

TEXTO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
MODELO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_template_message'
JANELA = 'apps.automation.mensageiro.janela.aberta'
OK = {'messages': [{'id': 'wamid.aviso-ok'}]}

STATUS_RELEVANTES = ['confirmed', 'out_for_delivery', 'ready', 'delivered', 'cancelled']


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield
    cache.clear()


@pytest.fixture
def pedido(db):
    dono = get_user_model().objects.create_user(username='dono-aviso-modelo', password='x')
    conta = WhatsAppAccount.objects.create(
        name='Conta Aviso', phone_number_id='pn-aviso', waba_id='wa-aviso',
        phone_number='+5563900000081', display_phone_number='+5563900000081',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )
    loja = Store.objects.create(owner=dono, name='Cê Saladas', slug='loja-aviso-modelo', whatsapp_account=conta)
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja)
    perfil.account = conta
    perfil.save()
    for evento in ('order_confirmed', 'order_out_for_delivery', 'order_ready',
                   'order_delivered', 'order_cancelled'):
        AutoMessage.objects.create(
            company=perfil, event_type=evento, name=evento,
            message_text='Oi {customer_name}, pedido {order_number}: {order_status}', is_active=True,
        )
    MessageTemplate.objects.create(
        account=conta, template_id='tpl-aviso', name=modelo.NOME_DO_MODELO, language='pt_BR',
        category='utility', status='approved', components=[],
    )
    return StoreOrder.objects.create(
        store=loja, total=Decimal('30'), subtotal=Decimal('30'),
        status='confirmed', payment_status='paid', payment_method='pix',
        customer_name='Maria', customer_phone='63999990801', delivery_method='delivery',
    )


def _avisar(pedido, status):
    automation_tasks.notify_order_status_change.apply(args=[str(pedido.id), status])


@pytest.mark.django_db
@pytest.mark.parametrize('status', STATUS_RELEVANTES)
def test_janela_fechada_nao_manda_nada(pedido, status):
    """Dono, 05/10: aviso de status é mensagem normal, só com janela de 24 h
    aberta. Fora dela não sai template (custo) nem texto (131047 certo)."""
    with patch(JANELA, return_value=False), patch(MODELO, return_value=OK) as por_modelo, \
            patch(TEXTO, return_value=OK) as por_texto:
        _avisar(pedido, status)

    por_modelo.assert_not_called()
    por_texto.assert_not_called()
    assert not Message.objects.filter(metadata__order_id=str(pedido.id)).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('status', STATUS_RELEVANTES)
def test_janela_aberta_sai_o_texto_da_loja(pedido, status):
    with patch(JANELA, return_value=True), patch(MODELO) as por_modelo, \
            patch(TEXTO, return_value=OK) as por_texto:
        _avisar(pedido, status)

    por_modelo.assert_not_called()
    texto = por_texto.call_args.kwargs.get('text') or por_texto.call_args.args[1]
    assert texto.startswith('Oi Maria, pedido ' + pedido.order_number)


@pytest.mark.django_db
def test_modo_humano_nao_cala_o_aviso_de_status(pedido):
    """Dono, 05/10 (Tassiana): quem muda o status é o atendente; o aviso sai
    mesmo com a conversa em modo humano (a regra de 21/09 calava)."""
    Conversation.objects.create(
        account=pedido.store.whatsapp_account, phone_number='5563999990801',
        mode=Conversation.ConversationMode.HUMAN,
    )
    with patch(JANELA, return_value=True), patch(MODELO) as por_modelo, \
            patch(TEXTO, return_value=OK) as por_texto:
        _avisar(pedido, 'out_for_delivery')

    por_modelo.assert_not_called()
    por_texto.assert_called_once()
