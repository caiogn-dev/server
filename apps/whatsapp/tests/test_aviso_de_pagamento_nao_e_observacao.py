"""Quem acabou de pagar não está mandando recado pra cozinha.

31/08, Dênia × Cê Saladas. Ela fechou o pedido CE-2608318490 no cartão, pagou
R$ 35,99 no Checkout Pro e voltou pelo botão do Mercado Pago, que abre o
WhatsApp com o texto pronto da página de sucesso:

    Olá! Gostaria de confirmar meu pedido #ac83efdc-c91e-4a23-bafa-c88e6b514e3a.

O bot respondeu:

    ✅ _Anotado: Olá! Gostaria de confirmar meu pedido #ac83efdc-…_
    💳 *Como prefere pagar?*

Ou seja: guardou a confirmação de pagamento como observação do pedido e pediu
pagamento de novo a quem já tinha pagado. Ela insistiu ("Já foi pago", "Foi
pago com cartão") e recebeu um SEGUNDO link de pagamento — risco de cobrar duas
vezes a mesma pessoa.

`_handle_notes_input` tinha só duas saídas: palavra de pular, ou observação.
Pedido de produto ganhou a terceira em 13/ago (caso Yeda). Aviso de pagamento é
a quarta — e a que custa mais caro, porque acontece exatamente no minuto em que
o dinheiro entra.
"""
from django.test import TestCase

from apps.stores.services.busca_de_produto import parece_aviso_de_pagamento


class ReconheceAvisoDePagamentoTests(TestCase):
    def test_o_texto_que_o_mercado_pago_devolve(self):
        # É o que a página de sucesso pré-preenche no wa.me. Com número de
        # pedido ou com o UUID cru, os dois circulam em produção.
        for texto in [
            'Olá! Gostaria de confirmar meu pedido #ac83efdc-c91e-4a23-bafa-c88e6b514e3a.',
            'Olá! Gostaria de confirmar meu pedido #CE-2608318490.',
            'Olá! Acabei de fazer um pedido e gostaria de confirmar.',
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(parece_aviso_de_pagamento(texto))

    def test_as_frases_que_o_cliente_escreve_sozinho(self):
        for texto in [
            'Já foi pago', 'ja foi pago', 'Foi pago com cartão', 'já paguei',
            'Paguei', 'acabei de pagar', 'PAGUEI AGORA', 'pagamento efetuado',
            'segue o comprovante', 'ta pago', 'tá pago', 'já fiz o pix',
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(parece_aviso_de_pagamento(texto), texto)

    def test_observacao_de_verdade_continua_sendo_observacao(self):
        # O guarda não pode engolir o recado real da cozinha. "sem cebola" e
        # "pagar na entrega" são coisas diferentes — a segunda é escolha de
        # forma de pagamento, não aviso de que o dinheiro já entrou.
        for texto in [
            'sem cebola', 'caprichar no molho', 'tocar a campainha',
            'entregar na portaria', 'sem salsinha por favor',
            'pode mandar sem tomate', 'apartamento 302',
        ]:
            with self.subTest(texto=texto):
                self.assertFalse(parece_aviso_de_pagamento(texto), texto)

    def test_texto_vazio_nao_estoura(self):
        for texto in ['', '   ', None]:
            with self.subTest(texto=texto):
                self.assertFalse(parece_aviso_de_pagamento(texto))
