"""
As duas regras da ANVISA que decidem se a etiqueta é válida ou só bonita.

RDC 429/2020 — a lupa preta "ALTO EM". IN 75/2020 — arredondamento e regra de
zero. Sem elas o painel calcula certo e imprime errado.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.nutrition.services.rotulagem import (
    alertas_frontais, arredondar, arredondar_tabela,
)


class AlertasFrontaisTest(SimpleTestCase):
    def test_solido_acima_do_limite_leva_lupa(self):
        r = alertas_frontais({"added_sugars_g": Decimal("20"),
                              "saturated_fat_g": Decimal("1"),
                              "sodium_mg": Decimal("100")})
        self.assertEqual(r["texto"], ["ALTO EM AÇÚCAR ADICIONADO"])
        self.assertTrue(r["conclusivo"])

    def test_exatamente_no_limite_ja_leva_lupa(self):
        # A norma diz "maior ou igual". 6,00 g de saturada leva selo.
        r = alertas_frontais({"added_sugars_g": Decimal("0"),
                              "saturated_fat_g": Decimal("6"),
                              "sodium_mg": Decimal("0")})
        self.assertEqual(r["texto"], ["ALTO EM GORDURA SATURADA"])

    def test_um_pouco_abaixo_do_limite_nao_leva(self):
        r = alertas_frontais({"added_sugars_g": Decimal("14.9"),
                              "saturated_fat_g": Decimal("5.99"),
                              "sodium_mg": Decimal("599")})
        self.assertEqual(r["texto"], [])

    def test_liquido_tem_limite_pela_metade(self):
        valores = {"added_sugars_g": Decimal("8"),
                   "saturated_fat_g": Decimal("0"),
                   "sodium_mg": Decimal("0")}
        self.assertEqual(alertas_frontais(valores, "solido")["texto"], [])
        self.assertEqual(alertas_frontais(valores, "liquido")["texto"],
                         ["ALTO EM AÇÚCAR ADICIONADO"])

    def test_os_tres_selos_de_uma_vez(self):
        r = alertas_frontais({"added_sugars_g": Decimal("30"),
                              "saturated_fat_g": Decimal("10"),
                              "sodium_mg": Decimal("900")})
        self.assertEqual(r["texto"], ["ALTO EM AÇÚCAR ADICIONADO",
                                      "ALTO EM GORDURA SATURADA",
                                      "ALTO EM SÓDIO"])

    def test_nutriente_sem_dado_nao_vira_ausencia_de_selo(self):
        # O perigo real: imprimir etiqueta limpa porque o dado faltava.
        r = alertas_frontais({"added_sugars_g": None,
                              "saturated_fat_g": Decimal("1"),
                              "sodium_mg": Decimal("10")})
        self.assertEqual(r["texto"], [])
        self.assertFalse(r["conclusivo"])
        self.assertEqual(r["indefinidos"], ["added_sugars_g"])

    def test_forma_invalida_falha_alto(self):
        with self.assertRaises(ValueError):
            alertas_frontais({}, "gasoso")


class ArredondamentoIN75Test(SimpleTestCase):
    def test_gordura_trans_residual_declara_zero(self):
        # 0,04 g está abaixo do piso de 0,2 g: a norma manda declarar 0.
        self.assertEqual(arredondar("trans_fat_g", Decimal("0.04")), Decimal("0"))

    def test_gordura_trans_acima_do_piso_mantem_uma_casa(self):
        self.assertEqual(arredondar("trans_fat_g", Decimal("0.24")), Decimal("0.2"))

    def test_energia_e_sodio_sao_inteiros(self):
        self.assertEqual(arredondar("energy_kcal", Decimal("123.4")), Decimal("123"))
        self.assertEqual(arredondar("sodium_mg", Decimal("456.7")), Decimal("457"))

    def test_sodio_residual_declara_zero(self):
        self.assertEqual(arredondar("sodium_mg", Decimal("4.9")), Decimal("0"))

    def test_carboidrato_uma_casa(self):
        self.assertEqual(arredondar("carbohydrates_g", Decimal("25.84")), Decimal("25.8"))

    def test_meio_arredonda_para_cima(self):
        self.assertEqual(arredondar("protein_g", Decimal("2.25")), Decimal("2.3"))

    def test_none_continua_none(self):
        self.assertIsNone(arredondar("protein_g", None))

    def test_tabela_inteira_de_uma_vez(self):
        saida = arredondar_tabela({"energy_kcal": Decimal("123.4"),
                                   "trans_fat_g": Decimal("0.04"),
                                   "protein_g": None})
        self.assertEqual(saida, {"energy_kcal": Decimal("123"),
                                 "trans_fat_g": Decimal("0"),
                                 "protein_g": None})
