"""
Declaração de lactose — RDC 136/2017.

Lactose não é alergênico (intolerância é enzima, não sistema imune), então tem
norma própria e ficou de fora da RDC 26. O dono da loja perguntou por que não
aparecia, e não aparecia porque ninguém tinha implementado.
"""
from django.test import SimpleTestCase

from apps.nutrition.lactose import (
    BAIXO_TEOR, CONTEM, ISENTO, NAO_REVISADO, ZERO, declaracao,
)


class DeclaracaoDeLactoseTest(SimpleTestCase):
    def test_tudo_isento_declara_que_nao_contem(self):
        self.assertEqual(declaracao([ISENTO, ISENTO])["texto"], "NÃO CONTÉM LACTOSE.")

    def test_um_com_lactose_contamina_o_prato(self):
        # Não é média: é o pior caso. Um ingrediente com lactose faz o prato
        # inteiro conter lactose.
        d = declaracao([ISENTO, ISENTO, CONTEM])
        self.assertEqual(d["estado"], CONTEM)
        self.assertEqual(d["texto"], "CONTÉM LACTOSE.")

    def test_zero_lactose_perde_para_baixo_teor(self):
        self.assertEqual(declaracao([ZERO, BAIXO_TEOR])["estado"], BAIXO_TEOR)

    def test_zero_lactose_ganha_de_isento(self):
        # "Zero lactose" é afirmação mais forte que "não contém por natureza":
        # o produto passou por processo, e é isso que a etiqueta deve dizer.
        self.assertEqual(declaracao([ISENTO, ZERO])["estado"], ZERO)

    def test_um_nao_revisado_impede_a_declaracao_inteira(self):
        # Mesma regra do alergênico: afirmar sobre cadastro que ninguém olhou
        # é pior que não afirmar.
        d = declaracao([ISENTO, ISENTO, NAO_REVISADO])
        self.assertFalse(d["revisado"])
        self.assertEqual(d["texto"], "")
        self.assertEqual(d["pendentes"], 1)

    def test_estado_desconhecido_conta_como_nao_revisado(self):
        d = declaracao([ISENTO, "seja_la_o_que_for"])
        self.assertFalse(d["revisado"])

    def test_receita_vazia_nao_declara(self):
        d = declaracao([])
        self.assertFalse(d["revisado"])
        self.assertEqual(d["texto"], "")
