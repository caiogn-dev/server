"""
Testes de segurança para _coords_from_maps_url e _is_safe_maps_url.

P0 — SSRF: StoreDeliveryFeeView é AllowAny. O campo `address` é user-controlled.
A guard original ('maps' in url OR 'goo.gl' in url) é bypassável com URLs como
http://169.254.169.254/maps ou http://redis:6379/goo.gl — o servidor faria
requests.get() para infra interna sem autenticação.

Correção: whitelist de hostnames Google Maps antes de qualquer chamada de rede.
"""
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase


def _import_fn():
    from apps.stores.api.views.storefront_views import (
        _coords_from_maps_url,
        _is_safe_maps_url,
    )
    return _coords_from_maps_url, _is_safe_maps_url


class TestIsSafeMapsUrl(SimpleTestCase):
    """_is_safe_maps_url só aceita domínios Google Maps conhecidos."""

    def setUp(self):
        _, self.fn = _import_fn()

    def test_maps_app_goo_gl_aceito(self):
        self.assertTrue(self.fn('https://maps.app.goo.gl/abc123'))

    def test_goo_gl_aceito(self):
        self.assertTrue(self.fn('https://goo.gl/maps/xyz'))

    def test_maps_google_com_aceito(self):
        self.assertTrue(self.fn('https://maps.google.com/?q=-23.5,-46.6'))

    def test_www_google_com_aceito(self):
        self.assertTrue(self.fn('https://www.google.com/maps?q=0,0'))

    def test_maps_googleapis_com_aceito(self):
        self.assertTrue(self.fn('https://maps.googleapis.com/'))

    def test_ip_de_metadata_bloqueado(self):
        """Bypass clássico de cloud metadata — host tem 'maps' no path."""
        self.assertFalse(self.fn('http://169.254.169.254/maps'))

    def test_localhost_bloqueado(self):
        self.assertFalse(self.fn('http://localhost/maps/api'))

    def test_redis_interno_bloqueado(self):
        self.assertFalse(self.fn('http://redis:6379/?x=goo.gl'))

    def test_host_evil_com_bloqueado(self):
        self.assertFalse(self.fn('http://evil.com/maps/foo'))

    def test_host_local_bloqueado(self):
        self.assertFalse(self.fn('http://internal.local/?q=goo.gl'))

    def test_ip_privado_bloqueado(self):
        self.assertFalse(self.fn('http://10.0.0.1/maps'))

    def test_url_vazia_retorna_false(self):
        self.assertFalse(self.fn(''))

    def test_url_none_retorna_false(self):
        self.assertFalse(self.fn(None))


def _make_final_resp(url='https://maps.google.com/@-23.5,-46.6,15z', text=''):
    """Resposta HTTP final (sem redirect)."""
    resp = MagicMock()
    resp.is_redirect = False
    resp.url = url
    resp.text = text
    return resp


def _make_redirect_resp(location):
    """Resposta HTTP de redirect (3xx) para um dado Location."""
    resp = MagicMock()
    resp.is_redirect = True
    resp.headers = {'Location': location}
    return resp


class TestCoordsFromMapsUrlSsrfGuard(SimpleTestCase):
    """requests.get NUNCA deve ser chamado para URLs fora da whitelist."""

    def setUp(self):
        self.fn, _ = _import_fn()

    def test_metadata_url_nao_faz_request(self):
        with patch('requests.get') as mock_get:
            result = self.fn('http://169.254.169.254/maps')
        mock_get.assert_not_called()
        self.assertIsNone(result)

    def test_localhost_nao_faz_request(self):
        with patch('requests.get') as mock_get:
            result = self.fn('http://localhost/maps/ssrf')
        mock_get.assert_not_called()
        self.assertIsNone(result)

    def test_ip_privado_nao_faz_request(self):
        with patch('requests.get') as mock_get:
            result = self.fn('http://10.10.10.10/maps')
        mock_get.assert_not_called()
        self.assertIsNone(result)

    def test_evil_com_nao_faz_request(self):
        with patch('requests.get') as mock_get:
            result = self.fn('http://evil.com/goo.gl/maps')
        mock_get.assert_not_called()
        self.assertIsNone(result)

    def test_url_com_coords_no_path_extrai_sem_request(self):
        """URL direta com coords (@lat,lng) — extrai sem chamada de rede."""
        url = 'https://maps.google.com/maps?q=@-23.5505,-46.6333'
        with patch('requests.get') as mock_get:
            result = self.fn(url)
        mock_get.assert_not_called()
        self.assertIsNotNone(result)
        lat, lng = result
        self.assertAlmostEqual(lat, -23.5505)
        self.assertAlmostEqual(lng, -46.6333)

    def test_shortlink_legitimo_chama_request(self):
        """Shortlink Google (maps.app.goo.gl) SIM deve fazer request."""
        with patch('requests.get', return_value=_make_final_resp()) as mock_get:
            result = self.fn('https://maps.app.goo.gl/AbCdEf')
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn('maps.app.goo.gl', call_url)

    def test_goo_gl_shortlink_chama_request(self):
        """goo.gl/maps SIM deve fazer request."""
        with patch('requests.get', return_value=_make_final_resp()) as mock_get:
            result = self.fn('https://goo.gl/maps/Xyz123')
        mock_get.assert_called_once()


class TestCoordsFromMapsUrlRedirectSsrf(SimpleTestCase):
    """Redirect via host da whitelist para destino interno deve ser bloqueado."""

    def setUp(self):
        self.fn, _ = _import_fn()

    def test_redirect_de_google_para_metadata_bloqueado(self):
        """www.google.com/url?q=http://169.254.169.254/maps — primeiro hop OK,
        redirect aponta para metadata; deve ser bloqueado sem fazer o 2º request."""
        redirect_resp = _make_redirect_resp('http://169.254.169.254/latest/meta-data/maps')
        with patch('requests.get', return_value=redirect_resp) as mock_get:
            result = self.fn('https://www.google.com/url?q=http://169.254.169.254/maps')
        self.assertIsNone(result)
        mock_get.assert_called_once()  # só o primeiro hop; o redirect é abortado

    def test_redirect_de_google_para_localhost_bloqueado(self):
        redirect_resp = _make_redirect_resp('http://localhost/maps/internal')
        with patch('requests.get', return_value=redirect_resp) as mock_get:
            result = self.fn('https://goo.gl/maps/abc')
        self.assertIsNone(result)
        mock_get.assert_called_once()

    def test_redirect_de_google_para_ip_privado_bloqueado(self):
        redirect_resp = _make_redirect_resp('http://10.0.0.1/maps')
        with patch('requests.get', return_value=redirect_resp) as mock_get:
            result = self.fn('https://maps.app.goo.gl/abc')
        self.assertIsNone(result)
        mock_get.assert_called_once()

    def test_redirect_legítimo_goo_gl_para_google_maps_aceito(self):
        """goo.gl → maps.google.com/maps@lat,lng — cadeia segura deve funcionar."""
        redirect_resp = _make_redirect_resp('https://maps.google.com/@-23.5,-46.6,15z')
        final_resp = _make_final_resp('https://maps.google.com/@-23.5,-46.6,15z')
        responses = [redirect_resp, final_resp]
        with patch('requests.get', side_effect=responses) as mock_get:
            result = self.fn('https://goo.gl/maps/abc123')
        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)
        lat, lng = result
        self.assertAlmostEqual(lat, -23.5)
        self.assertAlmostEqual(lng, -46.6)

    def test_redirect_para_evil_com_bloqueado(self):
        """Redirect da whitelist para domínio alheio — bloqueado."""
        redirect_resp = _make_redirect_resp('https://evil.com/steal?data=maps')
        with patch('requests.get', return_value=redirect_resp) as mock_get:
            result = self.fn('https://maps.app.goo.gl/abc')
        self.assertIsNone(result)
        mock_get.assert_called_once()
