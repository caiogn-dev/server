from django.test import SimpleTestCase

from apps.nutrition.categorias import e_estrangeira, mapa_de_categorias


class CategoriasTests(SimpleTestCase):
    def test_junta_acento_caixa_e_espaco(self):
        m = mapa_de_categorias({'À base de plantas': 5, 'a base de plantas': 2, 'A  Base de plantas ': 1})
        self.assertEqual(len(set(m.values())), 1)
        self.assertEqual(m['À base de plantas'], 'À base de plantas')

    def test_typo_de_uma_letra_vai_para_a_mais_usada(self):
        m = mapa_de_categorias({'Alho': 9, 'allho': 1})
        self.assertEqual(m['allho'], 'Alho')

    def test_nao_junta_palavras_curtas_diferentes(self):
        m = mapa_de_categorias({'Ovo': 3, 'Ovos': 3, 'Uva': 2, 'Uma': 1})
        self.assertEqual(m['Uva'], 'Uva')

    def test_estrangeira_some(self):
        m = mapa_de_categorias({'plant based foods': 4, 'Cereais e derivados': 10, 'productos lacteos': 1})
        self.assertIsNone(m['plant based foods'])
        self.assertIsNone(m['productos lacteos'])
        self.assertEqual(m['Cereais e derivados'], 'Cereais e derivados')

    def test_vazia_fica_vazia(self):
        self.assertEqual(mapa_de_categorias({'': 3})[''], '')

    def test_portugues_com_palavra_ambigua_nao_e_estrangeiro(self):
        self.assertFalse(e_estrangeira('Alimentos preparados'))
