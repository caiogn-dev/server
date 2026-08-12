"""
Declaração de alergênicos — RDC 26/2015 + Lei 10.674/2003 (glúten).

Alergênico não é detalhe de rótulo: é a informação que impede alguém de
passar mal. A frase tem que cair sozinha dos ingredientes, porque a mão
esquece o leite do purê.
"""
from django.test import SimpleTestCase

from apps.nutrition.allergens import declaracao, validar


class DeclaracaoTest(SimpleTestCase):
    def test_sem_alergenico_ainda_declara_gluten(self):
        # A Lei 10.674/2003 exige a frase do glúten em TODO alimento embalado,
        # inclusive no que não tem cereal nenhum.
        d = declaracao()
        self.assertEqual(d["texto"], "NÃO CONTÉM GLÚTEN.")

    def test_um_alergenico(self):
        d = declaracao(contem=["leite"])
        self.assertEqual(d["texto"], "ALÉRGICOS: CONTÉM LEITE. NÃO CONTÉM GLÚTEN.")

    def test_dois_alergenicos_usam_e(self):
        d = declaracao(contem=["leite", "ovo"])
        self.assertIn("CONTÉM LEITE E OVOS.", d["texto"])

    def test_tres_ou_mais_usam_virgula_e_e(self):
        d = declaracao(contem=["leite", "ovo", "soja"])
        self.assertIn("CONTÉM LEITE, OVOS E SOJA.", d["texto"])

    def test_cereal_do_grupo_dispara_contem_gluten(self):
        d = declaracao(contem=["trigo"])
        self.assertIn("CONTÉM TRIGO.", d["texto"])
        self.assertIn("CONTÉM GLÚTEN.", d["texto"])
        self.assertNotIn("NÃO CONTÉM GLÚTEN.", d["texto"])
        self.assertEqual(d["gluten"], "contem")

    def test_pode_conter_gera_frase_separada(self):
        d = declaracao(contem=["leite"], pode_conter=["amendoim"])
        self.assertIn("ALÉRGICOS: CONTÉM LEITE.", d["texto"])
        self.assertIn("ALÉRGICOS: PODE CONTER AMENDOIM.", d["texto"])

    def test_traco_de_cereal_vira_pode_conter_gluten(self):
        d = declaracao(pode_conter=["cevada"])
        self.assertIn("PODE CONTER GLÚTEN.", d["texto"])
        self.assertEqual(d["gluten"], "pode_conter")

    def test_alergenico_certo_nao_repete_como_pode_conter(self):
        # A norma proíbe usar "pode conter" para amaciar uma certeza.
        d = declaracao(contem=["leite"], pode_conter=["leite", "soja"])
        self.assertEqual(d["pode_conter"], ["soja"])
        self.assertNotIn("PODE CONTER LEITE", d["texto"])

    def test_ordem_segue_a_norma_nao_a_alfabetica(self):
        d = declaracao(contem=["soja", "leite", "ovo"])
        self.assertIn("CONTÉM LEITE, OVOS E SOJA.", d["texto"])

    def test_valida_chave_desconhecida(self):
        self.assertEqual(validar(["leite", "kriptonita"]), ["kriptonita"])
        self.assertEqual(validar(["leite", "trigo"]), [])
