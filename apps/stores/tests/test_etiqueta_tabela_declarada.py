"""
Zebra com a tabela PRONTA da loja (laudo/nutricionista).

O painel manda `declarada` junto da etiqueta. Os dois motores do servidor
(ZPL de texto e bitmap do layout desenhado) recalculavam a porção a partir do
valor por 100 g: 209 kcal × 3,3 = 689,7 → "690", e o laudo da Agrião diz 691.
"""
from django.test import SimpleTestCase

from apps.stores.services import etiquetas_layout as motor
from apps.stores.services.etiquetas_zpl import render_etiquetas

ET = {
    'name': 'Parmegiana de Frango', 'servingG': 330,
    'per100g': {'energy_kcal': 209, 'sodium_mg': 368},
    'ingredients': 'Filé de peito de frango, farinha de trigo.',
    'declarada': {
        'porcoesPorEmbalagem': '1', 'porcao': '330 g (1 marmita)', 'colunaPorcao': '330 g',
        'linhas': {'energy_kcal': ['209', '691', '35'], 'protein_g': ['16', '53', '106'],
                   'sodium_mg': ['368', '1216', '61']},
        'declaracoes': ['ZERO LACTOSE', 'CONTÉM GLÚTEN'],
    },
}


class EtiquetaTabelaDeclaradaTest(SimpleTestCase):
    def test_zpl_imprime_a_porcao_e_o_vd_declarados(self):
        zpl = render_etiquetas('nutricao', [ET], {})
        self.assertIn('691', zpl)
        self.assertNotIn('690', zpl)
        self.assertIn('1216', zpl)
        self.assertIn('106', zpl)
        self.assertIn('Porções por embalagem: 1', zpl)
        self.assertIn('330 g (1 marmita)', zpl)
        self.assertIn('CONTÉM GLÚTEN', zpl)
        self.assertIn('ZERO LACTOSE', zpl)

    def test_layout_desenhado_usa_as_linhas_e_o_cabecalho_declarados(self):
        linhas = {r[0]: r for r in motor.linhas_da_tabela(ET)}
        energia = next(v for k, v in linhas.items() if k.startswith('Valor energético'))
        self.assertEqual(energia[1:4], ('209', '691', '35'))
        self.assertEqual(motor.cabecalho_da_tabela(ET), ('Porções por embalagem: 1', 'Porção: 330 g (1 marmita)'))
        self.assertIn('CONTÉM GLÚTEN', motor.preencher('{allergens}', motor.dados_da_etiqueta(ET)))

    def test_campo_peso_vem_da_porcao_declarada(self):
        # Gramagem da marmita no layout desenhado: {peso} → "330 g".
        self.assertEqual(motor.preencher('Peso líquido: {peso}', motor.dados_da_etiqueta(ET)), 'Peso líquido: 330 g')

    def test_campo_peso_sem_tabela_usa_a_porcao_do_perfil(self):
        self.assertEqual(motor.preencher('{peso}', motor.dados_da_etiqueta({'name': 'X', 'servingG': 350})), '350 g')


class EstiloLaudoTest(SimpleTestCase):
    """Quadro no estilo do PDF do nutricionista: título só 1,25x a letra das
    linhas (no padrão ele ocupa 11% da altura e sai enorme)."""
    def _layout(self, estilo):
        return motor.validar_layout({'etiqueta': {'largura': 100, 'altura': 80}, 'papel': {'colunas': 1},
            'elementos': [{'id': 't', 'tipo': 'tabela', 'x': 15, 'y': 5, 'w': 70, 'h': 44, 'estilo': estilo}]})

    def test_estilo_laudo_e_aceito_e_preservado(self):
        self.assertEqual(self._layout('laudo')['elementos'][0]['estilo'], 'laudo')
        self.assertEqual(self._layout(None)['elementos'][0]['estilo'], 'padrao')

    def test_estilo_desconhecido_e_recusado(self):
        with self.assertRaises(motor.LayoutInvalido):
            self._layout('neon')

    def test_laudo_desenha_a_tabela_declarada(self):
        img = motor.render_bitmap(self._layout('laudo'), [ET])
        self.assertEqual(img.size, (800, 640))
        self.assertLess(sum(img.crop((120, 40, 680, 392)).getdata()) / (560 * 352), 255)  # tem tinta
