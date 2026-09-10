"""Endereço não pode ficar salvo como link do mapa nem como par de números.

Caso real: CE-2609103109, Cê Saladas, 10/set, lançado pelo PDV. O operador
colou o link curto do Google Maps que a cliente mandou no WhatsApp e o pedido
foi salvo com `street = "https://maps.app.goo.gl/i1Vcfc5fDj45Ja9U7"`. A
entrega até acontece — a coordenada existe —, mas a comanda, a etiqueta, o
relatório por bairro e o próximo pedido dessa cliente recebem um link.

O mesmo vale para "Localização enviada (-10.18314, -48.33626)", que é o rótulo
que o PDV escreve quando puxa o pin do WhatsApp.

Regras:
  1. Texto que é SÓ link ou SÓ coordenada vira nome de verdade, pela
     geocodificação reversa da coordenada.
  2. Nunca apagar: o link original sobrevive em `maps_url` e o texto em
     `raw_address`.
  3. Endereço escrito por gente não é tocado, e não gasta chamada de rede.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.stores.services.nome_do_lugar import (
    coordenadas_do_texto,
    e_so_um_ponto_no_mapa,
    nomear_se_for_so_um_ponto,
)

REVGEO = {
    'street': 'Avenida Juscelino Kubitscheck',
    'number': '38-76',
    'neighborhood': 'Plano Diretor Norte',
    'city': 'Palmas',
    'state': 'Tocantins',
    'state_code': 'TO',
    'zip_code': '77001-014',
    'formatted_address': 'Av. Juscelino Kubitscheck, 38-76 - Plano Diretor Norte, Palmas - TO',
}


class ReconhecerOPonto(TestCase):
    def test_link_do_maps_e_so_um_ponto(self):
        self.assertTrue(e_so_um_ponto_no_mapa('https://maps.app.goo.gl/i1Vcfc5fDj45Ja9U7'))
        self.assertTrue(e_so_um_ponto_no_mapa('https://www.google.com/maps/search/?api=1&query=-10.1,-48.3'))

    def test_par_de_numeros_e_so_um_ponto(self):
        self.assertTrue(e_so_um_ponto_no_mapa('-10.183138, -48.336260'))

    def test_rotulo_de_localizacao_enviada_e_so_um_ponto(self):
        self.assertTrue(e_so_um_ponto_no_mapa('Localização enviada (-10.18314, -48.33626)'))

    def test_endereco_de_gente_nao_e_ponto(self):
        self.assertFalse(e_so_um_ponto_no_mapa('Quadra 104 Norte, Alameda 10, casa 3'))
        self.assertFalse(e_so_um_ponto_no_mapa('Avenida JK 110 sul, Clínica DVI'))
        self.assertFalse(e_so_um_ponto_no_mapa(''))


class ExtrairCoordenada(TestCase):
    def test_do_par_cru(self):
        self.assertEqual(coordenadas_do_texto('-10.183138, -48.336260'), (-10.183138, -48.336260))

    def test_do_rotulo_do_pdv(self):
        self.assertEqual(coordenadas_do_texto('Localização enviada (-10.18314, -48.33626)'), (-10.18314, -48.33626))

    def test_do_link_de_busca(self):
        self.assertEqual(
            coordenadas_do_texto('https://www.google.com/maps/search/?api=1&query=-10.18314%2C-48.33626'),
            (-10.18314, -48.33626),
        )

    def test_do_link_com_arroba(self):
        self.assertEqual(
            coordenadas_do_texto('https://www.google.com/maps/@-10.18314,-48.33626,17z'),
            (-10.18314, -48.33626),
        )

    def test_o_pin_vence_o_centro_do_mapa(self):
        """No link longo do Maps, `@lat,lng` é o CENTRO da tela e `!3d!4d` é o PIN.

        No link real do CE-2609103109 os dois diferem 280 m em longitude
        (-48.3153351 vs -48.3127602). Ler o centro entrega na quadra errada.
        """
        url = ("https://www.google.com/maps/place/x/@-10.2566394,-48.3153351,17z"
               "/data=!3m1!4b1!4m4!3m3!8m2!3d-10.2566394!4d-48.3127602")
        self.assertEqual(coordenadas_do_texto(url), (-10.2566394, -48.3127602))

    def test_texto_sem_coordenada(self):
        self.assertIsNone(coordenadas_do_texto('Quadra 104 Norte, casa 3'))


class NomearOLugar(TestCase):
    def _com_revgeo(self, retorno=REVGEO):
        return patch('apps.stores.services.nome_do_lugar._reverse_geocode', return_value=retorno)

    def test_link_vira_endereco_de_verdade(self):
        with self._com_revgeo():
            saida = nomear_se_for_so_um_ponto({
                'address': 'https://maps.app.goo.gl/abc',
                'lat': -10.18314, 'lng': -48.33626,
            })
        self.assertEqual(saida['street'], 'Avenida Juscelino Kubitscheck')
        self.assertEqual(saida['neighborhood'], 'Plano Diretor Norte')
        self.assertEqual(saida['city'], 'Palmas')
        self.assertEqual(saida['state'], 'TO')
        self.assertEqual(saida['zip_code'], '77001-014')

    def test_o_link_original_nao_some(self):
        with self._com_revgeo():
            saida = nomear_se_for_so_um_ponto({
                'address': 'https://maps.app.goo.gl/abc', 'lat': -10.18314, 'lng': -48.33626,
            })
        self.assertEqual(saida['maps_url'], 'https://maps.app.goo.gl/abc')
        self.assertIn('maps.app.goo.gl/abc', saida['raw_address_original'])

    def test_coordenada_sai_do_proprio_texto_quando_nao_ha_lat_lng(self):
        with self._com_revgeo() as m:
            nomear_se_for_so_um_ponto({'address': 'Localização enviada (-10.18314, -48.33626)'})
        m.assert_called_once_with(-10.18314, -48.33626)

    def test_endereco_escrito_por_gente_passa_intacto_e_sem_rede(self):
        entrada = {'address': 'Quadra 104 Norte, casa 3', 'lat': -10.1, 'lng': -48.3}
        with self._com_revgeo() as m:
            saida = nomear_se_for_so_um_ponto(dict(entrada))
        m.assert_not_called()
        self.assertEqual(saida, entrada)

    def test_sem_coordenada_o_link_e_mantido_e_nada_quebra(self):
        entrada = {'address': 'https://maps.app.goo.gl/semcoords'}
        with patch('apps.stores.services.nome_do_lugar._coords_do_link_curto', return_value=None):
            with self._com_revgeo() as m:
                saida = nomear_se_for_so_um_ponto(dict(entrada))
        m.assert_not_called()
        self.assertEqual(saida['address'], 'https://maps.app.goo.gl/semcoords')

    def test_geocodificacao_muda_nao_apaga_o_que_ja_havia(self):
        with self._com_revgeo(None):
            saida = nomear_se_for_so_um_ponto({
                'address': 'https://maps.app.goo.gl/abc', 'lat': -10.1, 'lng': -48.3,
            })
        self.assertEqual(saida['address'], 'https://maps.app.goo.gl/abc')

    def test_complemento_escrito_por_gente_vence(self):
        with self._com_revgeo():
            saida = nomear_se_for_so_um_ponto({
                'address': '-10.18314,-48.33626', 'complement': 'Portaria B',
                'lat': -10.18314, 'lng': -48.33626,
            })
        self.assertEqual(saida['complement'], 'Portaria B')
