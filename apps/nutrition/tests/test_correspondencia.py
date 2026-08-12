"""
O casamento entre o ingrediente do lojista e o alimento da TACO.

Os casos aqui saíram do banco de verdade: são os nomes que a Cê Saladas e a
Agrião cadastraram, contra os nomes reais da TACO.
"""
from django.test import SimpleTestCase

from apps.nutrition.services.correspondencia import normalizar, pontuar, sugerir


class Falso:
    def __init__(self, display_name):
        self.display_name = display_name


class NormalizarTest(SimpleTestCase):
    def test_tira_acento_caixa_e_pontuacao(self):
        self.assertEqual(normalizar("Queijo, Muçarela"), "queijo mucarela")
        self.assertEqual(normalizar("  Alho-poró  "), "alho poro")


class PontuarTest(SimpleTestCase):
    def test_nome_curto_contido_no_da_taco(self):
        # "Abacaxi" x "Abacaxi, cru" — o caso mais comum do cadastro real.
        self.assertGreater(pontuar("Abacaxi", "Abacaxi, cru"), 0.8)

    def test_acento_faltando_nao_atrapalha(self):
        self.assertGreater(pontuar("Queijo mucarela", "Queijo, muçarela"), 0.8)

    def test_preparo_diferente_ainda_casa(self):
        self.assertGreater(pontuar("Mandioca cozida", "Mandioca, crua"), 0.7)

    def test_preparo_igual_fica_acima_do_diferente(self):
        # Desempate, não filtro: as duas são candidatas, mas a certa vem antes.
        self.assertGreater(pontuar("Mandioca cozida", "Mandioca, cozida"),
                           pontuar("Mandioca cozida", "Mandioca, crua"))

    def test_nome_curto_contra_variedade_da_taco(self):
        # O lojista escreve "Manga"; a TACO detalha a variedade. É o caso mais
        # comum do cadastro real e estava caindo fora do corte.
        self.assertGreater(pontuar("Manga", "Manga, Palmer, crua"), 0.8)
        self.assertGreater(pontuar("Palmito", "Palmito, pupunha, em conserva"), 0.8)

    def test_nao_confunde_com_alimento_que_so_cita_o_nome(self):
        # Casos reais que vinham empatados na frente do certo: cajá-manga é
        # outra fruta, e charuto de repolho é prato recheado.
        self.assertGreater(pontuar("Manga", "Manga, Haden, crua"),
                           pontuar("Manga", "Cajá-Manga, cru"))
        self.assertGreater(pontuar("Repolho", "Repolho, branco, cru"),
                           pontuar("Repolho", "Charuto, de repolho"))
        self.assertLess(pontuar("Repolho", "Charuto, de repolho"), 0.7)

    def test_comidas_diferentes_pontuam_baixo(self):
        self.assertLess(pontuar("Abacaxi", "Abacate, cru"), 0.55)
        self.assertLess(pontuar("Camarão a provençal", "Abacaxi, cru"), 0.4)

    def test_parte_nao_casa_com_o_todo(self):
        # O perigo do Jaccard sozinho: "tomate" está dentro de "molho de
        # tomate", mas são coisas nutricionalmente diferentes.
        self.assertLess(pontuar("Molho de tomate industrializado", "Tomate, cru"), 0.55)

    def test_vazio_nao_quebra(self):
        self.assertEqual(pontuar("", "Abacaxi, cru"), 0.0)
        self.assertEqual(pontuar("Abacaxi", ""), 0.0)


class SugerirTest(SimpleTestCase):
    def setUp(self):
        self.taco = [Falso(n) for n in (
            "Abacaxi, cru", "Abacate, cru", "Mandioca, crua", "Mandioca, cozida",
            "Queijo, muçarela", "Tomate, cru", "Camarão, cozido",
        )]

    def test_devolve_o_melhor_primeiro(self):
        r = sugerir("Mandioca cozida", self.taco)
        self.assertEqual(r[0][0].display_name, "Mandioca, cozida")

    def test_respeita_o_minimo(self):
        self.assertEqual(sugerir("Bobó de frango", self.taco, minimo=0.9), [])

    def test_limita_a_quantidade(self):
        r = sugerir("Mandioca", self.taco, minimo=0.1, quantos=2)
        self.assertEqual(len(r), 2)

    def test_lista_vazia_de_candidatos(self):
        self.assertEqual(sugerir("Abacaxi", []), [])
