"""Quem apertou "Parar promoções" não recebe o reengajamento automático.

Regra do dono (19/09): nenhuma mensagem de marketing para quem marcou que não
quer receber. As campanhas já respeitavam (lista + envio). O reengajamento
diário ("faz tempo que você não pede…") é promoção e NÃO consultava a lista
de saída — só as campanhas o faziam.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.campaigns.services.optout import registrar_saida
from apps.stores.tests.factories import make_store
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.tasks.automation_tasks import send_reengagement_message


@pytest.fixture
def conta(db):
    return WhatsAppAccount.objects.create(name='Conta Reeng', phone_number_id='pn-reeng', waba_id='wa-reeng')


def _janela_aberta(conta, telefone):
    from django.utils import timezone

    from apps.conversations.models import Conversation

    Conversation.objects.create(
        account=conta, phone_number=telefone, last_customer_message_at=timezone.now(),
    )


def _enviar(conta, telefone):
    loja = make_store()
    envio = MagicMock()
    with patch('apps.whatsapp.tasks.automation_tasks._get_store_profile', return_value=object()), \
            patch('apps.whatsapp.tasks.automation_tasks._get_account_for_profile', return_value=conta), \
            patch('apps.whatsapp.tasks.automation_tasks._reengagement_content', return_value=('oi', [])), \
            patch('apps.automation.mensageiro.enviar_botoes', envio):
        send_reengagement_message.run(telefone, str(loja.id))
    return envio


@pytest.mark.django_db
def test_quem_pediu_para_parar_nao_recebe_reengajamento(conta):
    registrar_saida(conta, '5563999990401', 'Parar promoções', 'button')

    envio = _enviar(conta, '5563999990401')

    envio.assert_not_called()


@pytest.mark.django_db
def test_mesmo_numero_em_outro_formato_tambem_e_barrado(conta):
    registrar_saida(conta, '5563999990402', 'Parar promoções', 'button')

    envio = _enviar(conta, '63999990402')

    envio.assert_not_called()


@pytest.mark.django_db
def test_cliente_que_nao_saiu_continua_recebendo(conta):
    # Desde 21/09 o reengajamento também exige janela de 24 h aberta: sem ela
    # a Meta recusa (131047) e o envio vira desperdício.
    _janela_aberta(conta, '5563999990403')

    envio = _enviar(conta, '5563999990403')

    envio.assert_called_once()


@pytest.mark.django_db
def test_fora_da_janela_nao_gasta_envio(conta):
    """Cliente inativo há semanas está fora das 24 h: não adianta tentar."""
    envio = _enviar(conta, '5563999990404')

    envio.assert_not_called()
