"""Cliente pede cartão, recebe cartão. Diz que o link não abre, recebe a máquina.

Pedido pelo dono em 14/ago:

    "AO FECHAR PEDIDO, É GERADO LINK PARA PAGAMENTO EM CRÉDITO/DÉBITO (...)
    ENVIAR LINK PIX APENAS SE FOR PIX, ENVIAR LINK DE PAGAMENTO CASO CARTÃO
    (...) e caso ele fale: 'não consigo pagar pelo link' ENVIAMOS A MÁQUINA!"

Antes disto o handler só sabia PIX. Como o padrão de detecção era
`quero pagar|forma de pagamento|como pago`, "quero pagar no cartão" casava com
`quero pagar` e o cliente recebia um código PIX. E quando dizia que o link não
abria, não havia resposta nenhuma — a venda morria com o pedido montado.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.whatsapp.intents.handlers.payment import PaymentStatusHandler


def _handler(pedido=None):
    h = PaymentStatusHandler.__new__(PaymentStatusHandler)
    h.account = MagicMock()
    h.conversation = MagicMock(phone_number='+5563984143551')
    h.company_profile = MagicMock()
    h.store = MagicMock()
    h._whatsapp_service = MagicMock()
    h._pedido_aberto = MagicMock(return_value=pedido)
    h._get_session_manager = MagicMock(
        return_value=MagicMock(is_payment_pending=MagicMock(return_value=False)),
    )
    return h


def _pedido():
    p = MagicMock()
    p.id = 'abc'
    p.order_number = 'CE-123'
    p.total = Decimal('47.74')
    p.pix_code = ''
    return p


class TestCartao:
    def test_pedir_cartao_gera_link_de_checkout(self):
        h = _handler(_pedido())

        with patch('apps.stores.services.checkout_service.CheckoutService.create_payment',
                   return_value={'success': True, 'init_point': 'https://mp/checkout/xyz'}) as cria:
            r = h.handle({'original_message': 'quero pagar no cartão'})

        assert cria.call_args.kwargs['payment_method'] == 'link'
        assert 'https://mp/checkout/xyz' in r.response_text

    def test_pedir_cartao_NAO_manda_pix(self):
        """O bug: 'quero pagar' casava com o padrão de PIX."""
        pedido = _pedido()
        pedido.pix_code = '00020126580014BR.GOV.BCB.PIX'
        h = _handler(pedido)

        with patch('apps.stores.services.checkout_service.CheckoutService.create_payment',
                   return_value={'success': True, 'init_point': 'https://mp/checkout/xyz'}):
            r = h.handle({'original_message': 'quero pagar no cartão'})

        assert '00020126580014' not in r.response_text

    def test_gateway_fora_do_ar_oferece_a_maquininha(self):
        """Sem link e sem alternativa, a venda morre montada."""
        h = _handler(_pedido())

        with patch('apps.stores.services.checkout_service.CheckoutService.create_payment',
                   return_value={'success': False, 'error': 'gateway fora'}):
            r = h.handle({'original_message': 'cartão'})

        assert 'maquin' in r.response_text.lower()


class TestMaquininha:
    def test_link_que_nao_abre_oferece_a_maquina(self):
        h = _handler(_pedido())

        r = h.handle({'original_message': 'não consigo pagar pelo link'})

        assert 'maquin' in r.response_text.lower()

    def test_nao_devolve_o_MESMO_link_que_o_cliente_disse_nao_abrir(self):
        h = _handler(_pedido())

        with patch('apps.stores.services.checkout_service.CheckoutService.create_payment') as cria:
            r = h.handle({'original_message': 'não consigo pagar pelo link'})

        cria.assert_not_called()
        assert 'http' not in r.response_text


class TestPixContinuaFuncionando:
    """O caminho antigo não pode regredir: PIX é a maioria das vendas.

    Estes dois passam pela consulta real de pedido pendente, então o `Order` do
    módulo é substituído — o resto do teste usa dublês.
    """

    @staticmethod
    def _com_pix():
        pedido = _pedido()
        pedido.pix_code = '00020126580014BR.GOV.BCB.PIX'
        h = _handler(pedido)
        consulta = MagicMock()
        consulta.filter.return_value.order_by.return_value.first.return_value = pedido
        return h, consulta

    def test_pedir_pix_manda_o_codigo(self):
        h, consulta = self._com_pix()

        with patch('apps.whatsapp.intents.handlers.payment.Order', objects=consulta):
            r = h.handle({'original_message': 'manda o pix'})

        assert '00020126580014' in r.response_text

    def test_sem_forma_declarada_segue_o_caminho_de_antes(self):
        """"como pago?" não é pedido de cartão — não pode virar link à força."""
        h, consulta = self._com_pix()

        with patch('apps.whatsapp.intents.handlers.payment.Order', objects=consulta), \
             patch('apps.stores.services.checkout_service.CheckoutService.create_payment') as cria:
            r = h.handle({'original_message': 'como pago?'})

        cria.assert_not_called()
        assert '00020126580014' in r.response_text

    def test_sem_pedido_aberto_nao_inventa_cobranca(self):
        h = _handler(None)

        with patch('apps.stores.services.checkout_service.CheckoutService.create_payment') as cria:
            h.handle({'original_message': 'quero pagar no cartão'})

        cria.assert_not_called()


class TestORoteamentoChegaNoHandler:
    """De nada adianta o handler saber cartão se a mensagem não chega nele.

    O nome `REQUEST_PIX` é histórico: hoje essa intenção roteia pagamento em
    geral. Sem cartão/maquininha no padrão, "tem maquininha?" caía em UNKNOWN e
    o cliente ficava sem resposta com o pedido montado.
    """

    @pytest.mark.parametrize('frase', [
        'quero pagar no cartão',
        'aceita cartão?',
        'no crédito',
        'débito',
        'tem maquininha?',
        'pago na entrega',
        'manda o pix',
    ])
    def test_frase_de_pagamento_vira_intencao_de_pagamento(self, frase):
        from apps.whatsapp.intents.detector import IntentDetector, IntentType

        d = IntentDetector(use_llm_fallback=False).detect(frase.lower())

        assert d['intent'] == IntentType.REQUEST_PIX, frase
