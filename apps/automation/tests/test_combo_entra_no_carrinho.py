"""A montagem terminada tem que PÔR o combo no carrinho.

Antes disto o bot conduzia a escolha inteira, dizia "Fechado! ✅" e o combo
sumia — a conversa toda terminava em nada e o cliente ficava achando que tinha
pedido.

O combo entra no MESMO `pending_order_items` dos produtos. É essa lista que a
finalização lê para criar o pedido, e `create_order_from_whatsapp` já aceita
linha de combo (`combo_id` + `group_selections`) desde 10/ago. Guardar combo
num lugar separado criaria dois carrinhos para o mesmo cliente.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.unified_service import UnifiedService


def _servico(itens_atuais=None):
    s = UnifiedService.__new__(UnifiedService)
    s.store = MagicMock()
    s.account = MagicMock()
    s.conversation = MagicMock()
    s.company = MagicMock()

    gerente = MagicMock()
    gerente.get_pending_order_items.return_value = list(itens_atuais or [])
    s._get_session_manager = MagicMock(return_value=gerente)
    s._gerente = gerente
    return s


ITEM = {
    'combo_id': 'combo-5',
    'quantity': 1,
    'group_selections': {'grupo-1': ['sabor-a'] * 5},
}


class TestOComboEntraNoCarrinho:
    def test_a_linha_e_salva_nos_itens_pendentes(self):
        s = _servico()

        with patch('apps.whatsapp.intents.handlers.interactive.InteractiveReplyHandler'):
            s._por_no_carrinho(ITEM)

        salvos = s._gerente.save_pending_order_items.call_args[0][0]
        assert ITEM in salvos

    def test_NAO_apaga_o_que_ja_estava_no_carrinho(self):
        """Combo que zera o carrinho faz o cliente perder o que já pediu."""
        s = _servico([{'product_id': 'p1', 'quantity': 2}])

        with patch('apps.whatsapp.intents.handlers.interactive.InteractiveReplyHandler'):
            s._por_no_carrinho(ITEM)

        salvos = s._gerente.save_pending_order_items.call_args[0][0]
        assert len(salvos) == 2

    def test_devolve_o_resumo_do_carrinho(self):
        s = _servico()

        with patch(
            'apps.whatsapp.intents.handlers.interactive.InteractiveReplyHandler',
        ) as Handler:
            Handler.return_value._texto_do_carrinho.return_value = '🛒 resumo aqui'
            texto = s._por_no_carrinho(ITEM)

        assert '🛒 resumo aqui' in texto


class TestNaoPodeSumirEmSILENCIO:
    def test_falha_ao_salvar_AVISA_o_cliente(self):
        """Dizer "Fechado!" sem ter salvado é a pior saída possível."""
        s = _servico()
        s._gerente.save_pending_order_items.side_effect = RuntimeError('sessão morreu')

        texto = s._por_no_carrinho(ITEM)

        assert 'não consegui' in texto.lower()

    def test_resumo_quebrado_ainda_confirma_que_entrou(self):
        s = _servico()

        with patch(
            'apps.whatsapp.intents.handlers.interactive.InteractiveReplyHandler',
            side_effect=RuntimeError('boom'),
        ):
            texto = s._por_no_carrinho(ITEM)

        assert 'adicionado' in texto.lower()
        s._gerente.save_pending_order_items.assert_called_once()
