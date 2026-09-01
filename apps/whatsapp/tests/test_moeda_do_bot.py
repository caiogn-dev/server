"""O bot fala R$ em português, na conversa inteira.

Na conversa da Dênia (31/08) o mesmo valor apareceu das duas formas, com quatro
minutos de diferença:

    💰 *Total: R$ 35,99*     ← resumo do pedido
    💰 *Total: R$ 35.99*     ← confirmação, logo depois

O resumo usava `.replace('.', ',')`; a confirmação (`_finalize_order`,
`_send_pix_confirmation`) usava `f"{...:.2f}"` puro. Sete cópias da mesma regra
espalhadas pelo arquivo, e as que faltavam eram justo as da hora do dinheiro.

Uma função só, e ela também põe o separador de milhar — a Ivoneth cobra
encomenda de R$ 2.384,80, e "R$ 2384,80" não é como se escreve preço.
"""
from decimal import Decimal

from django.test import TestCase

from apps.whatsapp.formatacao import moeda


class MoedaTest(TestCase):
    def test_usa_virgula_como_separador_decimal(self):
        self.assertEqual(moeda(35.99), 'R$ 35,99')
        self.assertEqual(moeda(Decimal('35.99')), 'R$ 35,99')

    def test_sempre_duas_casas(self):
        self.assertEqual(moeda(12), 'R$ 12,00')
        self.assertEqual(moeda(12.5), 'R$ 12,50')
        self.assertEqual(moeda(Decimal('0')), 'R$ 0,00')

    def test_separador_de_milhar(self):
        # A encomenda da Ivoneth. "R$ 2384,80" não é preço, é número.
        self.assertEqual(moeda(2384.80), 'R$ 2.384,80')
        self.assertEqual(moeda(Decimal('1000')), 'R$ 1.000,00')
        self.assertEqual(moeda(1234567.89), 'R$ 1.234.567,89')

    def test_sem_o_simbolo_quando_pedido(self):
        # Serve linha de item, onde o "R$" já veio antes.
        self.assertEqual(moeda(35.99, simbolo=False), '35,99')

    def test_nao_estoura_com_none(self):
        self.assertEqual(moeda(None), 'R$ 0,00')

    def test_arredonda_meio_centavo_pra_cima(self):
        # Preço de combo dividido por 3 gera dízima; truncar perde centavo.
        self.assertEqual(moeda(Decimal('10.005')), 'R$ 10,01')


class MensagensDoCheckoutTest(TestCase):
    """As mensagens da hora do dinheiro não podem falar em inglês."""

    def test_nenhuma_mensagem_do_handler_usa_ponto_decimal(self):
        # Peneira contra a regressão: `:.2f` cru dentro de f-string de mensagem
        # é exatamente o que produziu "R$ 35.99".
        import re
        from pathlib import Path

        alvo = Path('apps/whatsapp/intents/handlers/base.py').read_text(encoding='utf-8')
        suspeitas = [
            linha.strip()
            for linha in alvo.splitlines()
            if 'R$ {' in linha and ':.2f}' in linha and ".replace('.', ',')" not in linha
        ]
        self.assertEqual(
            suspeitas, [],
            'valor em R$ formatado com ponto decimal:\n  ' + '\n  '.join(suspeitas),
        )
