"""Sugestão de endereço no lado errado de Palmas vai para o fim da lista.

22/10, Agrião: para "Alameda 2, 407 Norte" a 1ª sugestão era "407 norte -
Jardim Aureny III (Taquaralto)" — o texto diz "norte", mas o ponto fica
13 km ao SUL, no Taquaralto. Quem toca na primeira opção vai para lá.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.stores.services.endereco_de_palmas import ponto_contradiz_o_setor
from apps.stores.services.geo.service import GeoService

AURENY = {'display_name': '407 norte - Jardim Aureny III (Taquaralto), Palmas - TO, Brasil',
          'lat': -10.2815616, 'lng': -48.3373482}
CERTA = {'display_name': 'Quadra 407 Norte Alameda 2, 2 - Arno, Palmas - TO, Brasil',
         'lat': -10.162021, 'lng': -48.3540569}
SUL = {'display_name': 'Quadra 407 Sul Alameda 2 - Plano Diretor Sul, Palmas - TO, Brasil',
       'lat': -10.2058, 'lng': -48.3524}


class PontoContradizOSetorTest(SimpleTestCase):
    def test_norte_digitado_e_ponto_no_sul(self):
        self.assertTrue(ponto_contradiz_o_setor('Alameda 2, 407 Norte', AURENY))

    def test_norte_digitado_e_ponto_no_norte(self):
        self.assertFalse(ponto_contradiz_o_setor('Alameda 2, 407 Norte', CERTA))

    def test_sul_digitado_e_ponto_no_sul(self):
        self.assertFalse(ponto_contradiz_o_setor('407 sul alameda 2', SUL))

    def test_sul_digitado_e_ponto_no_norte(self):
        self.assertTrue(ponto_contradiz_o_setor('407 sul alameda 2', CERTA))

    def test_sem_setor_no_texto_nao_julga(self):
        self.assertFalse(ponto_contradiz_o_setor('Rua das Flores', AURENY))

    def test_fora_de_palmas_nao_julga(self):
        porto = {'display_name': 'Rua 407 Norte, Porto Nacional - TO', 'lat': -10.70, 'lng': -48.41}
        self.assertFalse(ponto_contradiz_o_setor('407 Norte', porto))

    def test_sem_coordenada_nao_julga(self):
        self.assertFalse(ponto_contradiz_o_setor('407 Norte', {'display_name': AURENY['display_name']}))


class AutosuggestOrdenaPeloLadoTest(SimpleTestCase):
    def test_lado_errado_vai_para_o_fim(self):
        geo = GeoService()
        with patch.object(geo.provider, 'autosuggest', return_value=[AURENY, CERTA]):
            res = geo.autosuggest('Alameda 2, 407 Norte')
        self.assertEqual([r['display_name'] for r in res], [CERTA['display_name'], AURENY['display_name']])
