"""
A notação do IBGE decide se a etiqueta conclui ou não.

Na seção "Convenções" da POF: "-" é dado numérico igual a ZERO (não resultante
de arredondamento) e "..." é dado NÃO DISPONÍVEL. Tratar o hífen como nulo — o
erro óbvio, e o que eu tinha escrito na primeira versão — deixaria 1.520
alimentos sem açúcar de adição e nenhuma receita fecharia a lupa frontal,
quando na verdade a POF está afirmando que o alimento não tem açúcar
adicionado.

Errar para o outro lado é pior ainda: um nulo virando zero omitiria um selo
"ALTO EM" obrigatório.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.nutrition.management.commands.import_pof_table import _numero, _preparo, _titulo


class NotacaoIBGETest(SimpleTestCase):
    def test_hifen_e_zero_medido(self):
        self.assertEqual(_numero("-"), Decimal("0"))

    def test_reticencias_e_ausencia(self):
        self.assertIsNone(_numero("..."))

    def test_nao_se_aplica_e_ausencia(self):
        self.assertIsNone(_numero(".."))
        self.assertIsNone(_numero("NAO SE APLICA"))

    def test_omitido_e_ausencia(self):
        self.assertIsNone(_numero("x"))

    def test_vazio_e_ausencia(self):
        self.assertIsNone(_numero(""))
        self.assertIsNone(_numero(None))

    def test_numero_normal(self):
        self.assertEqual(_numero("9.527"), Decimal("9.527"))

    def test_virgula_decimal(self):
        self.assertEqual(_numero("48,067"), Decimal("48.067"))

    def test_zero_explicito_continua_zero(self):
        self.assertEqual(_numero("0,0"), Decimal("0.0"))

    def test_negativo_vira_nulo(self):
        # Composição negativa é erro de digitação da fonte, não medição.
        self.assertIsNone(_numero("-1,5"))

    def test_texto_solto_nao_quebra(self):
        self.assertIsNone(_numero("aproximado"))


class CamposDeTextoTest(SimpleTestCase):
    def test_preparo_vazio_quando_nao_se_aplica(self):
        self.assertEqual(_preparo("NAO SE APLICA"), "")
        self.assertEqual(_preparo("COZIDO(A)"), "COZIDO(A)")

    def test_titulo_tira_o_caixa_alta_da_pof(self):
        self.assertEqual(_titulo("ARROZ INTEGRAL"), "Arroz Integral")
        self.assertEqual(_titulo("  MILHO   (EM GRAO) "), "Milho (Em Grao)")
