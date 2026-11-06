"""Pedido de localização com o botão nativo do WhatsApp ("Enviar localização").

A Cloud API tem `interactive.type = location_request_message`: o cliente toca
no botão e o WhatsApp abre o envio de localização direto — nada de achar o
📎. Se a API recusar o interativo, o cliente recebe o texto com o 📎.
"""
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.whatsapp.intents.handlers.base import HandlerResult
from apps.whatsapp.pedir_localizacao import PEDIR_LOCALIZACAO, PEDIR_LOCALIZACAO_BOTAO


EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]')
PINO_E_CLIPE = ('📍', '📎', '📌')


def sem_emoji_de_localizacao(texto):
    return not any(e in texto for e in PINO_E_CLIPE)


def test_textos_exatos_do_dono_sem_emoji():
    """Dono 06/11: emoji de pino/clipe na mensagem parece botão — o cliente toca nele."""
    assert PEDIR_LOCALIZACAO_BOTAO == (
        "Para calcular a entrega, toque no botão *Enviar localização* abaixo. "
        "Se preferir, digite o endereço com número e bairro."
    )
    assert PEDIR_LOCALIZACAO == (
        "Para calcular a entrega, me mande sua localização: no WhatsApp, toque em "
        "*Anexar* (clipe, ou + no iPhone) → *Localização* → *Enviar localização atual*. "
        "Ou digite o endereço com número e bairro."
    )
    for texto in (PEDIR_LOCALIZACAO, PEDIR_LOCALIZACAO_BOTAO):
        assert not EMOJI.search(texto), texto
        assert 'alfinete' not in texto.lower()


def test_regra_do_llm_proibe_alfinete_e_emoji_de_pino_e_clipe():
    from apps.whatsapp.pedir_localizacao import REGRA_LLM_PEDIR_LOCALIZACAO as regra

    assert PEDIR_LOCALIZACAO in regra
    assert 'NUNCA use a palavra "alfinete"' in regra
    for e in PINO_E_CLIPE:
        assert e in regra  # nomeados na proibição
    assert 'emoji' in regra.lower()


def test_handler_result_de_pedido_de_localizacao():
    r = HandlerResult.location_request(body='corpo', fallback_text='texto 📎')
    assert r.use_interactive is True
    assert r.interactive_type == 'location_request'
    assert r.interactive_data['body'] == 'corpo'
    assert r.interactive_data['fallback_text'] == 'texto 📎'
    # Quem só sabe mandar texto (tasks, outros canais) manda o texto com 📎.
    assert r.response_text == 'texto 📎'


def test_pedido_padrao_usa_os_dois_textos_com_prefixo():
    from apps.whatsapp.intents.handlers.base import pedido_de_localizacao

    r = pedido_de_localizacao('Não achei.')
    assert r.interactive_data['body'] == 'Não achei.\n\n' + PEDIR_LOCALIZACAO_BOTAO
    assert r.interactive_data['fallback_text'] == 'Não achei.\n\n' + PEDIR_LOCALIZACAO


def test_api_monta_o_payload_da_cloud_api():
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

    api = WhatsAppAPIService.__new__(WhatsAppAPIService)
    api.phone_number_id = 'PH1'
    with patch.object(WhatsAppAPIService, '_make_request', return_value={'messages': [{'id': 'w1'}]}) as req:
        api.send_location_request(to='5563999999999', body_text='corpo', reply_to='wamid.X')
    payload = req.call_args.kwargs['data']
    assert payload['type'] == 'interactive'
    assert payload['to'] == '5563999999999'
    assert payload['interactive'] == {
        'type': 'location_request_message',
        'body': {'text': 'corpo'},
        'action': {'name': 'send_location'},
    }
    assert payload['context'] == {'message_id': 'wamid.X'}


def _envio(resposta_do_svc):
    from apps.automation.services.unified_service import ResponseSource, UnifiedResponse
    from apps.whatsapp.services.webhook_service import WebhookService

    resposta = UnifiedResponse(
        content='corpo', source=ResponseSource.HANDLER,
        interactive_type='location_request',
        interactive_data={'body': 'corpo', 'fallback_text': 'texto 📎'},
    )
    event = SimpleNamespace(account=SimpleNamespace(id='acc-1'))
    message = SimpleNamespace(from_number='5563999999999', whatsapp_message_id='wamid.X', id='m1')
    svc = MagicMock()
    resposta_do_svc(svc)
    with patch('apps.whatsapp.services.message_service.MessageService', return_value=svc):
        WebhookService.__new__(WebhookService)._send_unified_interactive(event, message, resposta)
    return svc


def test_webhook_envia_o_botao():
    svc = _envio(lambda s: None)
    svc.send_location_request.assert_called_once()
    kw = svc.send_location_request.call_args.kwargs
    assert kw['body_text'] == 'corpo'
    assert kw['to'] == '5563999999999'
    svc.send_text_message.assert_not_called()


def test_api_recusou_o_botao_cai_para_o_texto_com_clipe():
    def _falha(s):
        s.send_location_request.side_effect = RuntimeError('(#131009) Parameter value is not valid')
    svc = _envio(_falha)
    svc.send_text_message.assert_called_once()
    assert svc.send_text_message.call_args.kwargs['text'] == 'texto 📎'


def _handler_de_entrega(cls, endereco_salvo=None, pickup=True):
    h = cls.__new__(cls)
    h.store = MagicMock(delivery_enabled=True, pickup_enabled=pickup, min_order_value=None,
                        address='Rua da Loja, 1', city='Palmas')
    sm = MagicMock()
    sm.get_delivery_address_info.return_value = endereco_salvo or {}
    h._get_session_manager = lambda: sm
    return h


def test_pergunta_de_entrega_sem_endereco_vem_com_o_botao():
    from apps.whatsapp.intents.handlers.info import DeliveryInfoHandler

    r = _handler_de_entrega(DeliveryInfoHandler).handle({'original_message': 'vocês entregam?'})
    assert r.interactive_type == 'location_request'
    assert PEDIR_LOCALIZACAO_BOTAO in r.interactive_data['body']
    assert PEDIR_LOCALIZACAO in r.interactive_data['fallback_text']
    assert 'Retirada' in r.interactive_data['body']
    assert sem_emoji_de_localizacao(r.interactive_data['body'])
    assert sem_emoji_de_localizacao(r.interactive_data['fallback_text'])


def test_pergunta_de_taxa_sem_endereco_vem_com_o_botao():
    from apps.whatsapp.intents.handlers.catalog import PriceCheckHandler

    r = _handler_de_entrega(PriceCheckHandler).handle({'original_message': 'qual a taxa de entrega?'})
    assert r.interactive_type == 'location_request'
    assert PEDIR_LOCALIZACAO_BOTAO in r.interactive_data['body']


def test_com_endereco_salvo_nao_pede_localizacao():
    from apps.whatsapp.intents.handlers.info import DeliveryInfoHandler

    salvo = {'address': 'Q. 110 Sul Alameda 3, 51', 'fee': 7.0, 'distance_km': 1.5}
    r = _handler_de_entrega(DeliveryInfoHandler, salvo).handle({'original_message': 'entrega?'})
    assert r.interactive_type != 'location_request'
