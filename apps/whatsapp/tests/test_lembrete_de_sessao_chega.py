"""Lembrete de carrinho abandonado do bot chega — com ou sem nome, e com retry.

Produção (medido em 15/set): 93 de 105 sessões do bot em 30 dias não têm
`customer_name`. `(nome or '').split()[0]` estourava `IndexError` e nenhuma
dessas pessoas recebia o lembrete — 6 "list index out of range" no log entre
05 e 08/set.

E o retry nunca adiantava: a chave de idempotência era reservada antes do envio
e não era liberada no erro, então a nova tentativa caía em "Duplicate … skipped".
Liberar a chave só pode acontecer se a mensagem NÃO saiu — senão o cliente
recebe duas.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.automation.models import CompanyProfile, CustomerSession
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.tasks import automation_tasks

User = get_user_model()
ENVIO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_interactive_buttons'
OK = {'messages': [{'id': 'wamid.sessao-ok'}]}


@pytest.fixture(autouse=True)
def cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def sessao(db):
    dono = User.objects.create_user(username='dono_lembrete_sessao', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Lembrete', slug='loja-lembrete-sessao')
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja)
    return CustomerSession.objects.create(
        company=perfil, session_id='sess-lembrete', phone_number='5563992338269',
        status='cart_created', customer_name='',
    )


def _rodar(sessao, tipo='20min'):
    # Conta real: o lembrete passa pelo MessageService, que grava a mensagem
    # e busca a conta no banco.
    conta = WhatsAppAccount.objects.create(
        name='Conta Sessao', phone_number_id='pn-sessao', waba_id='wa-sessao',
        phone_number='+5563900000091', display_phone_number='+5563900000091',
        access_token_encrypted='x', webhook_verify_token='x', owner=sessao.company.store.owner,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )
    with patch.object(automation_tasks, '_get_account_for_profile', return_value=conta), \
         patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        return automation_tasks.send_session_cart_reminder.apply(args=[str(sessao.id), tipo], throw=False)


@pytest.mark.django_db
class TestLembreteDeSessao:

    def test_cliente_sem_nome_recebe(self, sessao):
        with patch(ENVIO, return_value=OK) as envio:
            _rodar(sessao)

        envio.assert_called_once()
        assert envio.call_args.kwargs['body_text'].startswith('Oi, você!')

    def test_nome_so_de_espacos_tambem(self, sessao):
        sessao.customer_name = '   '
        sessao.save(update_fields=['customer_name'])
        with patch(ENVIO, return_value=OK) as envio:
            _rodar(sessao)

        envio.assert_called_once()

    def test_usa_o_primeiro_nome_quando_tem(self, sessao):
        sessao.customer_name = 'Priscila Maracaipe'
        sessao.save(update_fields=['customer_name'])
        with patch(ENVIO, return_value=OK) as envio:
            _rodar(sessao)

        assert envio.call_args.kwargs['body_text'].startswith('Oi, Priscila!')

    def test_falha_antes_de_enviar_tenta_de_novo(self, sessao):
        with patch(ENVIO, side_effect=[RuntimeError('rede caiu'), OK]) as envio:
            _rodar(sessao)

        assert envio.call_count == 2

    def test_falha_depois_de_enviar_nao_manda_duas_vezes(self, sessao):
        with patch(ENVIO, return_value=OK) as envio, \
             patch.object(CustomerSession, 'add_notification', side_effect=[RuntimeError('db'), None]):
            _rodar(sessao)

        envio.assert_called_once()

    def test_fica_gravado_na_conversa_como_automatico(self, sessao):
        from apps.whatsapp.models import Message
        with patch(ENVIO, return_value=OK):
            _rodar(sessao)

        msg = Message.objects.get(direction='outbound', to_number__endswith='992338269')
        assert msg.metadata.get('automatico') is True
        assert msg.metadata.get('evento') == 'session_cart_reminder'
