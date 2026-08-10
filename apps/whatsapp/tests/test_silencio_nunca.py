"""
Mensagem sem resposta é o pior desfecho do pipeline — e era silencioso.

Conversa de 09/ago:

    16:59:56  CLIENTE  Serve quantas pessoas?          → processed_by_agent=False
    17:02:16  CLIENTE  Quero fazer um jantar para as visitas, o que recomenda?
                                                        → processed_by_agent=False
    17:12:39  CLIENTE  Em
    17:13:50  CLIENTE  (repete a pergunta)             ← 14 minutos depois

Quando todo caminho falha, o código já registrava `[pipeline] MESSAGE DROPPED`
— um log de ERROR que ninguém lê em tempo real, enquanto o cliente acha que
está falando com uma parede. Em loja de comida, 14 minutos de silêncio é a
venda perdida.

Agora o último recurso responde: reconhece, não inventa, e oferece um humano.
"""
from unittest.mock import MagicMock, patch

from apps.whatsapp.services.webhook_service import WebhookService


def _evento():
    ev = MagicMock()
    ev.account.id = 'acc-1'
    return ev


def _mensagem():
    msg = MagicMock()
    msg.id = 'msg-1'
    msg.from_number = '5563999999999'
    msg.whatsapp_message_id = 'wamid.1'
    msg.text_body = 'Serve quantas pessoas?'
    return msg


def test_responde_em_vez_de_ficar_em_silencio():
    svc = WebhookService()

    with patch.object(WebhookService, '_send_unified_interactive') as envio, \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        enviou = svc._ultimo_recurso(_evento(), _mensagem())

    assert enviou is True
    envio.assert_called_once()


def test_a_resposta_oferece_um_humano():
    """Sem saída para humano, o último recurso é só mais uma parede."""
    svc = WebhookService()
    capturado = {}

    def _captura(self, event, message, resposta):
        capturado['r'] = resposta

    with patch.object(WebhookService, '_send_unified_interactive', _captura), \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        svc._ultimo_recurso(_evento(), _mensagem())

    ids = [b['id'] for b in (capturado['r'].buttons or [])]
    assert 'contact_support' in ids


def test_nao_promete_nem_inventa():
    svc = WebhookService()
    capturado = {}

    def _captura(self, event, message, resposta):
        capturado['r'] = resposta

    with patch.object(WebhookService, '_send_unified_interactive', _captura), \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        svc._ultimo_recurso(_evento(), _mensagem())

    texto = capturado['r'].content.lower()
    for proibido in ('r$', 'preço', 'entrega grátis', 'cardápio completo'):
        assert proibido not in texto


def test_falha_no_envio_nao_propaga():
    """Este é o último recurso: se ele estourar, a exceção não tem para onde ir."""
    svc = WebhookService()

    with patch.object(WebhookService, '_send_unified_interactive', side_effect=RuntimeError('meta fora')), \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        assert svc._ultimo_recurso(_evento(), _mensagem()) is False
