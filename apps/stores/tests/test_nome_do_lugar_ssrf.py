"""Regressão: _coords_do_link_curto não pode seguir links arbitrários (SSRF).

O campo `street` do endereço é dado externo (PDV, bot, checkout). Um operador
malicioso que passe uma URL arbitrária — AWS metadata, rede interna, serviço
privado — não pode fazer o servidor disparar uma requisição HTTP para lá.

Só domínios do Google Maps são permitidos. Tudo mais retorna o endereço
original sem tocar na rede.
"""
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase

from apps.stores.services.nome_do_lugar import (
    _coords_do_link_curto,
    nomear_se_for_so_um_ponto,
    _eh_url_google_maps,
)


class TestSsrfWhitelistLinkCurto(SimpleTestCase):
    """_coords_do_link_curto só segue URLs de domínios Google Maps."""

    def _head_ok(self, final_url):
        resp = MagicMock()
        resp.url = final_url
        return resp

    def test_maps_app_goo_gl_e_permitido(self):
        url = 'https://maps.app.goo.gl/i1Vcfc5fDj45Ja9U7'
        destino = 'https://www.google.com/maps/@-10.1833,-48.3339,17z'
        with patch('requests.head', return_value=self._head_ok(destino)) as mock:
            resultado = _coords_do_link_curto(url)
        mock.assert_called_once()
        self.assertIsNotNone(resultado)

    def test_goo_gl_maps_e_permitido(self):
        url = 'https://goo.gl/maps/abc123'
        destino = 'https://www.google.com/maps/@-10.0,-48.0,15z'
        with patch('requests.head', return_value=self._head_ok(destino)) as mock:
            _coords_do_link_curto(url)
        mock.assert_called_once()

    def test_aws_metadata_nao_e_permitido(self):
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('http://169.254.169.254/latest/meta-data/')
        mock.assert_not_called()
        self.assertIsNone(resultado)

    def test_ip_interno_nao_e_permitido(self):
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('http://192.168.1.1/admin')
        mock.assert_not_called()
        self.assertIsNone(resultado)

    def test_dominio_arbitrario_nao_e_permitido(self):
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('https://evil.com/ssrf')
        mock.assert_not_called()
        self.assertIsNone(resultado)

    def test_dominio_com_maps_no_path_nao_e_permitido(self):
        # Evita bypass por substring: evil.com/maps não é Google Maps
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('https://evil.com/maps/coordinates')
        mock.assert_not_called()
        self.assertIsNone(resultado)

    def test_dominio_falso_com_goo_gl_no_path_nao_e_permitido(self):
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('https://evil.com/?redirect=goo.gl')
        mock.assert_not_called()
        self.assertIsNone(resultado)

    def test_localhost_nao_e_permitido(self):
        with patch('requests.head') as mock:
            resultado = _coords_do_link_curto('http://localhost:8000/internal')
        mock.assert_not_called()
        self.assertIsNone(resultado)


class TestNomearSeFors_SoUmPontoSsrf(SimpleTestCase):
    """nomear_se_for_so_um_ponto não dispara requests para URLs não-Maps."""

    def test_endereco_com_url_arbitraria_nao_faz_request(self):
        endereco = {'street': 'http://169.254.169.254/latest/meta-data/'}
        with patch('requests.head') as mock:
            nomear_se_for_so_um_ponto(endereco)
        mock.assert_not_called()

    def test_endereco_com_dominio_interno_nao_faz_request(self):
        endereco = {'street': 'https://internal.service.local/api/secret'}
        with patch('requests.head') as mock:
            nomear_se_for_so_um_ponto(endereco)
        mock.assert_not_called()

    def test_endereco_sem_link_nao_faz_request(self):
        endereco = {'street': 'Rua das Flores, 123', 'neighborhood': 'Centro'}
        with patch('requests.head') as mock:
            resultado = nomear_se_for_so_um_ponto(endereco)
        mock.assert_not_called()
        self.assertEqual(resultado, endereco)


class TestEhUrlGoogleMaps(SimpleTestCase):
    """_eh_url_google_maps discrimina por HOSTNAME, não por substring."""

    def test_maps_app_goo_gl(self):
        self.assertTrue(_eh_url_google_maps('https://maps.app.goo.gl/xyz'))

    def test_goo_gl_maps(self):
        self.assertTrue(_eh_url_google_maps('https://goo.gl/maps/abc'))

    def test_maps_google_com(self):
        self.assertTrue(_eh_url_google_maps('https://maps.google.com/?q=10,20'))

    def test_www_google_com_maps(self):
        self.assertTrue(_eh_url_google_maps('https://www.google.com/maps/@10,20,15z'))

    def test_maps_google_com_br(self):
        self.assertTrue(_eh_url_google_maps('https://maps.google.com.br/maps'))

    def test_evil_com_nao_e_maps(self):
        self.assertFalse(_eh_url_google_maps('https://evil.com/maps'))

    def test_evil_com_goo_gl_no_path_nao_e_maps(self):
        self.assertFalse(_eh_url_google_maps('https://evil.com/?goo.gl'))

    def test_ip_nao_e_maps(self):
        self.assertFalse(_eh_url_google_maps('http://169.254.169.254/'))

    def test_none_nao_e_maps(self):
        self.assertFalse(_eh_url_google_maps(None))

    def test_string_vazia_nao_e_maps(self):
        self.assertFalse(_eh_url_google_maps(''))
