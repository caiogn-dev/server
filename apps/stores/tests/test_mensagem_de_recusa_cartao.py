"""A recusa do cartão precisa dizer ao cliente o que fazer.

31/08: o cartão do Jardel (CE-2608310043, R$ 86,39) foi recusado com
`invalid_card_token` e a tela mostrou "The following transactions failed" —
mensagem crua da Orders API, em inglês. O cliente não tem como saber que
bastava digitar o cartão de novo. Ele desistiu do cartão e pagou no PIX.
"""
from django.test import TestCase

from apps.stores.services import mp_orders

RECUSA_TOKEN = {
    'errors': [{'code': 'failed', 'message': 'The following transactions failed',
                'details': ['PAY01M1C026DWJ8ZW8P3K7MPMTSFC: invalid_card_token']}],
    'data': {'status': 'failed', 'transactions': {'payments': [
        {'status': 'failed', 'status_detail': 'invalid_card_token'}]}},
}


class MensagemDeRecusaTests(TestCase):
    def test_token_invalido_pede_para_digitar_o_cartao_de_novo(self):
        msg = mp_orders.mensagem_de_recusa('invalid_card_token')
        self.assertIn('cartão', msg.lower())
        self.assertNotIn('invalid_card_token', msg)

    def test_saldo_insuficiente_tem_texto_proprio(self):
        self.assertIn('limite', mp_orders.mensagem_de_recusa('cc_rejected_insufficient_amount').lower())

    def test_codigo_de_seguranca_tem_texto_proprio(self):
        msg = mp_orders.mensagem_de_recusa('cc_rejected_bad_filled_security_code')
        self.assertIn('segurança', msg.lower())

    def test_recusa_desconhecida_nao_vaza_ingles(self):
        msg = mp_orders.mensagem_de_recusa('algo_que_o_mp_inventou_amanha')
        self.assertNotIn('algo_que_o_mp', msg)
        self.assertTrue(msg.strip())

    def test_interpret_devolve_o_detalhe_do_pagamento_nao_o_texto_generico(self):
        """O motivo real mora no pagamento; `message` é sempre o mesmo genérico."""
        _ok, _status, _pid, detalhe = mp_orders.interpret(402, RECUSA_TOKEN)
        self.assertEqual(detalhe, 'invalid_card_token')
