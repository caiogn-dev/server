"""Canal único: a mensagem automática é gravada, marcada e não conta como resposta.

19/09: seis tarefas chamavam `WhatsAppAPIService` direto — 79 lembretes e
reengajamentos enviados em 30 dias, 1 visível nas conversas do painel. E os
envios que já gravavam (status, avaliação) atualizavam
`last_agent_message_at`: um "saiu para entrega" tirava o cliente da Fila
humana como se alguém tivesse respondido.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.automation.mensageiro import EnvioFalhou, enviar_botoes, enviar_texto
from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount

TEXTO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
BOTOES = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_interactive_buttons'
OK = {'messages': [{'id': 'wamid.canal-ok'}]}
TEL = '5563999990601'


@pytest.fixture(autouse=True)
def _api_sem_token():
    # O construtor decifra o token da conta; aqui só interessa o envio.
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-canal', password='x')
    return WhatsAppAccount.objects.create(
        name='Conta Canal', phone_number_id='pn-canal', waba_id='wa-canal',
        phone_number='+5563900000061', display_phone_number='+5563900000061',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )


@pytest.fixture
def conversa(conta):
    return Conversation.objects.create(account=conta, phone_number=TEL, contact_name='Cliente')


@pytest.mark.django_db
class TestCanal:
    def test_texto_fica_gravado_e_marcado_como_automatico(self, conta, conversa):
        with patch(TEXTO, return_value=OK):
            msg = enviar_texto(conta, TEL, 'Seu PIX está esperando', evento='pix_reminder')

        gravada = Message.objects.get(pk=msg.pk)
        assert gravada.direction == 'outbound'
        assert gravada.text_body == 'Seu PIX está esperando'
        assert gravada.metadata.get('automatico') is True
        assert gravada.metadata.get('evento') == 'pix_reminder'

    def test_botoes_ficam_gravados(self, conta, conversa):
        with patch(BOTOES, return_value=OK):
            msg = enviar_botoes(conta, TEL, 'Esqueceu algo?', [{'id': 'b1', 'title': 'Ver sacola'}],
                                evento='cart_reminder')

        assert Message.objects.filter(pk=msg.pk, metadata__evento='cart_reminder').exists()

    def test_automatica_nao_conta_como_a_loja_respondeu(self, conta, conversa):
        with patch(TEXTO, return_value=OK):
            enviar_texto(conta, TEL, 'Seu pedido saiu para entrega', evento='order_out_for_delivery')

        conversa.refresh_from_db()
        assert conversa.last_agent_message_at is None

    def test_falha_do_whatsapp_vira_erro_para_tentar_de_novo(self, conta, conversa):
        with patch(TEXTO, side_effect=Exception('meta fora do ar')):
            with pytest.raises(EnvioFalhou):
                enviar_texto(conta, TEL, 'oi', evento='pix_reminder')
