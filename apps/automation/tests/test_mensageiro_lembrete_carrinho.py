"""Lembrete de carrinho do site pelo canal: sai uma vez só e fica gravado.

Mesma história do lembrete de PIX: `send_cart_reminder` chamava
`WhatsAppAPIService` direto e o dono nunca via o que a loja mandou.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store, StoreCart, StoreCartItem, StoreProduct
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.tasks import automation_tasks

BOTOES = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_interactive_buttons'
OK = {'messages': [{'id': 'wamid.carrinho-ok'}]}
TEL = '5563999990801'


@pytest.fixture(autouse=True)
def _limpo():
    cache.clear()
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield
    cache.clear()


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-conta-cart', password='x')
    return WhatsAppAccount.objects.create(
        name='Conta Carrinho', phone_number_id='pn-cart', waba_id='wa-cart',
        phone_number='+5563900000081', display_phone_number='+5563900000081',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )


@pytest.fixture
def carrinho(db):
    dono = get_user_model().objects.create_user(username='dono-loja-cart', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Carrinho', slug='loja-lembrete-carrinho')
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja)
    AutoMessage.objects.create(
        company=perfil, event_type='cart_abandoned', name='Carrinho abandonado',
        message_text='Oi {customer_name}, seu carrinho:\n{cart_items}', is_active=True,
    )
    produto = StoreProduct.objects.create(store=loja, name='Salada', slug='salada', price=Decimal('30'))
    cart = StoreCart.objects.create(
        store=loja, session_key='cart-lembrete',
        metadata={'customer_phone': TEL, 'customer_name': 'Bia'},
    )
    StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)
    return cart


def _rodar(conta, carrinho, tipo='30min'):
    with patch.object(automation_tasks, '_get_account_for_profile', return_value=conta):
        return automation_tasks.send_cart_reminder.apply(args=[str(carrinho.id), tipo], throw=False)


@pytest.mark.django_db
class TestLembreteDeCarrinho:

    def test_fica_gravado_na_conversa_como_automatico(self, conta, carrinho):
        with patch(BOTOES, return_value=OK) as envio:
            _rodar(conta, carrinho)

        assert envio.call_args.kwargs['buttons'][0]['id'] == f'checkout_{carrinho.id}'
        msg = Message.objects.get(account=conta, direction='outbound')
        assert msg.text_body.startswith('Oi Bia, seu carrinho:')
        assert msg.metadata.get('automatico') is True
        assert msg.metadata.get('evento') == 'cart_reminder'

    def test_segunda_execucao_nao_repete(self, conta, carrinho):
        with patch(BOTOES, return_value=OK) as envio:
            _rodar(conta, carrinho)
            _rodar(conta, carrinho)

        envio.assert_called_once()

    def test_carrinho_vazio_nao_recebe(self, conta, carrinho):
        carrinho.items.all().delete()
        with patch(BOTOES, return_value=OK) as envio:
            _rodar(conta, carrinho)

        envio.assert_not_called()

    def test_falha_antes_de_enviar_tenta_de_novo(self, conta, carrinho):
        with patch(BOTOES, side_effect=[RuntimeError('rede caiu'), OK]) as envio:
            _rodar(conta, carrinho)

        assert envio.call_count == 2
