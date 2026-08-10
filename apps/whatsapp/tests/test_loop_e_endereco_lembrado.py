"""
Dois becos sem saída da conversa de 09/ago (conversa 0f7a3119).

BECO 1 — o loop de 4 minutos (17:04 → 17:08):

    BOT      Quer continuar seu pedido ou ver o cardápio?
    CLIENTE  ✅ Continuar pedido
    BOT      Não encontrei pagamentos pendentes. Quer fazer um pedido novo?
    CLIENTE  Sim
    BOT      Quer continuar seu pedido ou ver o cardápio?      ← volta ao começo

Duas causas somadas: `continue_checkout` roteava para o PaymentStatusHandler
(clicar "continuar pedido" ia consultar PAGAMENTO, não retomar o carrinho), e o
AffirmativeHandler respondia "Sim" com exatamente os mesmos dois botões de onde
o cliente tinha acabado de sair.

BECO 2 — o endereço esquecido (20:23):

    CLIENTE  📍 Localização
    BOT      ✅ Entregamos aí! Taxa de entrega (1.5 km): R$ 7,00
    CLIENTE  Esse é o endereço de entrega
    BOT      Me envie sua localização pelo alfinete do WhatsApp   ← 15s depois

`_delivery_info_text()` é um template estático que nunca olhou a sessão.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import CustomerSession
from apps.whatsapp.intents.handlers.base import IntentHandler


class _Handler(IntentHandler):
    """Instância mínima só para exercitar os helpers de texto."""

    def handle(self, intent_data):  # pragma: no cover - não usado
        return None


def _handler_com_endereco(endereco, taxa):
    h = _Handler.__new__(_Handler)
    h.account = MagicMock()
    h.conversation = MagicMock()
    h.company_profile = MagicMock()
    h.store = MagicMock()
    h.store.delivery_enabled = True
    h.store.pickup_enabled = False
    h.store.min_order_value = None
    h.store.address = 'Rua da Loja, 1'
    h.store.city = 'Palmas'

    sm = MagicMock()
    sm.get_delivery_address_info.return_value = {
        'address': endereco, 'fee': taxa, 'distance_km': 1.5,
        'duration_minutes': 3, 'lat': -10.2, 'lng': -48.3, 'address_components': {},
    }
    h._get_session_manager = lambda: sm
    return h


def test_nao_pede_localizacao_de_novo_quando_ja_tem_endereco():
    h = _handler_com_endereco('Q. 110 Sul Alameda 3, 51 - Palmas/TO', 7.0)

    texto = h._build_delivery_info_text()

    assert 'alfinete' not in texto.lower()
    assert 'Q. 110 Sul Alameda 3, 51' in texto
    assert '7,00' in texto or '7.00' in texto


def test_pede_localizacao_quando_ainda_nao_tem_endereco():
    h = _handler_com_endereco('', None)

    texto = h._build_delivery_info_text()

    assert 'alfinete' in texto.lower()


def test_endereco_sem_taxa_calculada_ainda_confirma_o_endereco():
    """Endereço digitado à mão pode não ter taxa; não pode virar pedido de GPS."""
    h = _handler_com_endereco('Q. 110 Sul Alameda 3, 51', None)

    texto = h._build_delivery_info_text()

    assert 'Q. 110 Sul Alameda 3, 51' in texto


# ── Beco 1: o loop ───────────────────────────────────────────────────────────

def _interactive_com_status(status):
    from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
    h = InteractiveReplyHandler.__new__(InteractiveReplyHandler)
    h.account = MagicMock()
    h.conversation = MagicMock()
    h.company_profile = MagicMock()
    h.store = MagicMock()
    sessao = MagicMock()
    sessao.status = status
    sm = MagicMock()
    sm.get_or_create_session.return_value = sessao
    h._get_session_manager = lambda: sm
    return h


def test_continuar_pedido_sem_pagamento_pendente_manda_o_cardapio():
    """Sem pagamento pendente, "Continuar pedido" retoma o PEDIDO."""
    h = _interactive_com_status(CustomerSession.SessionStatus.CART_CREATED)
    esperado = object()

    with patch('apps.whatsapp.intents.handlers.interactive.MenuRequestHandler') as menu, \
         patch('apps.whatsapp.intents.handlers.payment.PaymentStatusHandler') as pagamento:
        menu.return_value.handle.return_value = esperado
        resultado = h.handle({'reply_id': 'continue_checkout', 'reply_title': '', 'original_message': ''})

    assert resultado is esperado
    pagamento.assert_not_called()


def test_continuar_pedido_com_pagamento_pendente_ainda_consulta_pagamento():
    """Quem tem PIX aberto precisa do status — esse caminho não pode sumir."""
    h = _interactive_com_status(CustomerSession.SessionStatus.PAYMENT_PENDING)
    esperado = object()

    with patch('apps.whatsapp.intents.handlers.payment.PaymentStatusHandler') as pagamento:
        pagamento.return_value.handle.return_value = esperado
        resultado = h.handle({'reply_id': 'continue_checkout', 'reply_title': '', 'original_message': ''})

    assert resultado is esperado


def test_afirmativo_com_carrinho_nao_repete_os_mesmos_botoes():
    """"Sim" não pode devolver o mesmo par de botões que originou a pergunta."""
    import inspect
    from apps.whatsapp.intents.handlers import fallback

    fonte = inspect.getsource(fallback.AffirmativeHandler)
    assert 'Quer continuar seu pedido ou ver o cardápio?' not in fonte, (
        'o AffirmativeHandler devolvia exatamente a pergunta anterior — loop'
    )
