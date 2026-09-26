"""Pedido digitado: "sem X" tira, não pede — e a observação não se perde.

25/09, conversa real com a Cê Saladas (pedido CE-2609251646). A cliente
escreveu:

    Vou querer uma espécie filé de frango, sem tomate cereja e sem cebola
    roxa, se poder acrescentar cenoura ralada no lugar eu agradeço

O bot pôs no carrinho **1x Cebola roxa — R$ 2,99** (o complemento que ela
pediu para TIRAR), ignorou a salada de R$ 39,99 e jogou fora as três
observações. O PIX saiu de R$ 22,29; a atendente recalculou na mão.

Causa: `_parse_items_from_text_dynamic` devolvia o primeiro produto cujo nome
aparecesse no texto, sem olhar se estava dentro de "sem …". A regra de negação
já existia em `busca_de_produto` — este caminho é que não a usava.

Aquele extrator não existe mais: o pedido digitado passa pela triagem
(`test_porta_unica_do_texto_livre.py`, onde moram os casos de item, quantidade
e observação que ficavam aqui).
"""
from django.test import TestCase

from apps.stores.services.busca_de_produto import separar_negacoes

FRASE = (
    'Vou querer uma espécie filé de frango, sem tomate cereja e sem cebola roxa , '
    'se poder acrescentar cenoura ralada no lugar eu agradeço 🥹'
)


class SepararNegacoesTest(TestCase):
    def test_tira_os_trechos_negados_e_devolve_os_dois_lados(self):
        pedido, negados = separar_negacoes(FRASE)
        self.assertIn('espécie filé de frango', pedido.lower())
        self.assertNotIn('cebola', pedido.lower())
        self.assertNotIn('tomate', pedido.lower())
        self.assertEqual([n.lower() for n in negados], ['sem tomate cereja', 'sem cebola roxa'])

    def test_sem_negacao_devolve_a_frase_inteira(self):
        pedido, negados = separar_negacoes('quero 2 combos de 5 saladas')
        self.assertEqual(pedido, 'quero 2 combos de 5 saladas')
        self.assertEqual(negados, [])

    def test_sempre_nao_e_negacao(self):
        pedido, negados = separar_negacoes('quero o de sempre')
        self.assertEqual(negados, [])
