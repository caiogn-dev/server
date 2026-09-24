"""Aviso de status fora da janela de 24 h sai por MODELO aprovado, não por texto.

Medido de 21/09 a 24/09/2026: `order_confirmed` falhou 10 de 25 vezes e
`order_preparing` 5 de 18 — todas com 131047 ("Re-engagement message"). São
clientes do SITE: nunca mandaram mensagem, logo nunca houve janela. 50
pessoas em 3 dias ficaram sem saber que o pedido foi confirmado.

Texto livre só passa com janela aberta. Fora dela a Meta aceita um modelo
de utilidade aprovado — `aviso_de_pedido` — com nome, número, loja e a frase
do status como variáveis.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.automation.mensageiro import enviar_texto, modelo
from apps.stores.models import Store
from apps.whatsapp.models import Message, MessageTemplate, WhatsAppAccount

TEXTO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
MODELO = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_template_message'
JANELA = 'apps.automation.mensageiro.janela.aberta'
OK = {'messages': [{'id': 'wamid.modelo-ok'}]}
TEL = '5563999990701'
EXTRA = {'order_number': 'CE-2609240001', 'customer_name': 'Maria', 'source': 'store_order_notification'}


@pytest.fixture(autouse=True)
def _api_sem_token():
    with patch('apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.__init__', return_value=None):
        yield


@pytest.fixture
def conta(db):
    dono = get_user_model().objects.create_user(username='dono-modelo', password='x')
    conta = WhatsAppAccount.objects.create(
        name='Conta Modelo', phone_number_id='pn-modelo', waba_id='wa-modelo',
        phone_number='+5563900000071', display_phone_number='+5563900000071',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
        status=WhatsAppAccount.AccountStatus.ACTIVE,
    )
    Store.objects.create(owner=dono, name='Cê Saladas', slug='loja-modelo', whatsapp_account=conta)
    return conta


def _aprovado(conta, status='approved'):
    return MessageTemplate.objects.create(
        account=conta, template_id='tpl-1', name=modelo.NOME_DO_MODELO, language='pt_BR',
        category='utility', status=status, components=[],
    )


class TestFrases:
    def test_todo_status_que_o_pedido_avisa_tem_frase(self):
        for evento in ('order_confirmed', 'order_preparing', 'order_ready', 'order_out_for_delivery',
                       'order_delivered', 'order_cancelled', 'order_paid'):
            assert modelo.FRASES[evento]

    def test_frase_nao_tem_quebra_de_linha_nem_tab(self):
        # A Meta recusa variável com \n ou \t (erro 132018).
        for frase in modelo.FRASES.values():
            assert '\n' not in frase and '\t' not in frase


class TestComponentes:
    def test_quatro_variaveis_na_ordem_nome_pedido_loja_frase(self):
        comp = modelo.componentes('Maria', 'CE-1', 'Cê Saladas', 'foi confirmado')
        assert comp == [{'type': 'body', 'parameters': [
            {'type': 'text', 'text': 'Maria'},
            {'type': 'text', 'text': 'CE-1'},
            {'type': 'text', 'text': 'Cê Saladas'},
            {'type': 'text', 'text': 'foi confirmado'},
        ]}]

    def test_sem_nome_vira_cliente(self):
        comp = modelo.componentes('', 'CE-1', 'Loja', 'x')
        assert comp[0]['parameters'][0]['text'] == 'Cliente'


@pytest.mark.django_db
class TestCanalForaDaJanela:

    def test_janela_fechada_com_modelo_aprovado_sai_por_modelo(self, conta):
        _aprovado(conta)
        with patch(JANELA, return_value=False), patch(MODELO, return_value=OK) as por_modelo, \
                patch(TEXTO) as por_texto:
            msg = enviar_texto(conta, TEL, 'Olá Maria! Seu pedido foi confirmado', 'order_confirmed', extra=EXTRA)

        por_texto.assert_not_called()
        kwargs = por_modelo.call_args.kwargs
        assert kwargs['template_name'] == modelo.NOME_DO_MODELO
        params = kwargs['components'][0]['parameters']
        assert [p['text'] for p in params] == ['Maria', 'CE-2609240001', 'Cê Saladas', modelo.FRASES['order_confirmed']]
        assert msg.message_type == Message.MessageType.TEMPLATE
        assert msg.metadata['automatico'] is True
        assert msg.metadata['evento'] == 'order_confirmed'
        assert msg.metadata['por_modelo'] is True

    def test_janela_aberta_continua_texto_livre(self, conta):
        # Texto livre é o da loja (personalizável); o modelo é só a saída de emergência.
        _aprovado(conta)
        with patch(JANELA, return_value=True), patch(MODELO) as por_modelo, patch(TEXTO, return_value=OK) as por_texto:
            enviar_texto(conta, TEL, 'Olá!', 'order_confirmed', extra=EXTRA)
        por_modelo.assert_not_called()
        por_texto.assert_called_once()

    def test_sem_modelo_aprovado_tenta_o_texto_como_antes(self, conta):
        _aprovado(conta, status='pending')
        with patch(JANELA, return_value=False), patch(MODELO) as por_modelo, patch(TEXTO, return_value=OK) as por_texto:
            enviar_texto(conta, TEL, 'Olá!', 'order_confirmed', extra=EXTRA)
        por_modelo.assert_not_called()
        por_texto.assert_called_once()

    def test_evento_que_nao_e_status_de_pedido_nao_usa_o_modelo(self, conta):
        _aprovado(conta)
        with patch(JANELA, return_value=False), patch(MODELO) as por_modelo, patch(TEXTO, return_value=OK):
            enviar_texto(conta, TEL, 'Seu carrinho…', 'cart_reminder', extra={})
        por_modelo.assert_not_called()

    def test_nao_consulta_a_janela_quando_nao_ha_modelo(self, conta):
        # Sem modelo não há alternativa: a consulta seria uma query a mais por aviso, à toa.
        with patch(JANELA) as janela, patch(TEXTO, return_value=OK):
            enviar_texto(conta, TEL, 'Olá!', 'order_confirmed', extra=EXTRA)
        janela.assert_not_called()


@pytest.mark.django_db
class TestCriarNaMeta:

    def test_cria_o_modelo_de_utilidade_e_grava_a_linha(self, conta):
        criar = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService._make_request'
        with patch(criar, return_value={'id': '123', 'status': 'PENDING', 'category': 'UTILITY'}) as req:
            linha = modelo.criar_na_meta(conta)

        args = req.call_args
        assert args.args[0] == 'POST' and args.args[1] == 'wa-modelo/message_templates'
        corpo = args.kwargs['data']
        assert corpo['name'] == modelo.NOME_DO_MODELO
        assert corpo['category'] == 'UTILITY'
        assert corpo['language'] == 'pt_BR'
        body = next(c for c in corpo['components'] if c['type'] == 'BODY')
        assert '{{1}}' in body['text'] and '{{4}}' in body['text']
        assert len(body['example']['body_text'][0]) == 4
        assert linha.template_id == '123' and linha.status == 'pending'

    def test_criar_duas_vezes_nao_duplica(self, conta):
        _aprovado(conta)
        criar = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService._make_request'
        with patch(criar) as req:
            linha = modelo.criar_na_meta(conta)
        req.assert_not_called()
        assert linha.status == 'approved'
