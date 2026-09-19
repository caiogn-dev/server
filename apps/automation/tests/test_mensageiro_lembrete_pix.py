"""Lembrete de PIX pelo canal: sai uma vez só e fica gravado na conversa.

Até 19/09 `send_payment_reminder` chamava `WhatsAppAPIService` direto: o
cliente recebia, o painel não mostrava nada. Os testes de comportamento
(pedido pago não recebe, segunda execução não repete, falha antes do envio
libera a nova tentativa) já valiam antes da troca e têm que continuar valendo.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.tasks import automation_tasks

TEXTO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
OK = {'messages': [{'id': 'wamid.pix-ok'}]}
TEL = '5563999990701'


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield
    cache.clear()


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-conta-pix', password='x')
    return WhatsAppAccount.objects.create(
        name='Conta PIX', phone_number_id='pn-pix', waba_id='wa-pix',
        phone_number='+5563900000071', display_phone_number='+5563900000071',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )


@pytest.fixture
def pedido(db):
    dono = get_user_model().objects.create_user(username='dono-loja-pix', password='x')
    loja = Store.objects.create(owner=dono, name='Loja PIX', slug='loja-lembrete-pix')
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja)
    AutoMessage.objects.create(
        company=perfil, event_type='pix_reminder', name='Lembrete de PIX',
        message_text='Oi {customer_name}, falta pagar {amount}.', is_active=True,
    )
    return StoreOrder.objects.create(
        store=loja, total=Decimal('42.00'), subtotal=Decimal('42.00'),
        status='pending', payment_status='pending', payment_method='pix',
        customer_name='Rita', customer_phone=TEL,
    )


def _rodar(conta, pedido, tipo='first'):
    with patch.object(automation_tasks, '_get_account_for_profile', return_value=conta):
        return automation_tasks.send_payment_reminder.apply(args=[str(pedido.id), tipo], throw=False)


@pytest.mark.django_db
class TestLembreteDePix:

    def test_fica_gravado_na_conversa_como_automatico(self, conta, pedido):
        with patch(TEXTO, return_value=OK):
            _rodar(conta, pedido)

        msg = Message.objects.get(account=conta, direction='outbound')
        assert msg.text_body.startswith('Oi Rita, falta pagar')
        assert msg.metadata.get('automatico') is True
        assert msg.metadata.get('evento') == 'pix_reminder'

    def test_marca_o_pedido(self, conta, pedido):
        with patch(TEXTO, return_value=OK):
            _rodar(conta, pedido)

        pedido.refresh_from_db()
        assert 'payment_reminder_first_sent' in pedido.metadata

    def test_pedido_pago_nao_recebe(self, conta, pedido):
        pedido.payment_status = 'paid'
        pedido.save(update_fields=['payment_status'])
        with patch(TEXTO, return_value=OK) as envio:
            _rodar(conta, pedido)

        envio.assert_not_called()

    def test_segunda_execucao_nao_repete(self, conta, pedido):
        with patch(TEXTO, return_value=OK) as envio:
            _rodar(conta, pedido)
            _rodar(conta, pedido)

        envio.assert_called_once()

    def test_falha_antes_de_enviar_tenta_de_novo(self, conta, pedido):
        with patch(TEXTO, side_effect=[RuntimeError('rede caiu'), OK]) as envio:
            _rodar(conta, pedido)

        assert envio.call_count == 2
        # A tentativa que caiu fica gravada como falha; a que saiu, como enviada.
        status = sorted(Message.objects.filter(account=conta, direction='outbound').values_list('status', flat=True))
        assert status == sorted([Message.MessageStatus.FAILED, Message.MessageStatus.SENT])
