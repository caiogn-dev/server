"""Testes do guard de SSRF para URLs de webhook (A5)."""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.url_security import validate_public_webhook_url


class ValidatePublicWebhookUrlTestCase(SimpleTestCase):
    def _bad(self, url):
        with self.assertRaises(ValidationError, msg=f'esperava rejeitar {url}'):
            validate_public_webhook_url(url)

    def test_rejects_non_http_schemes(self):
        self._bad('file:///etc/passwd')
        self._bad('ftp://example.com/x')
        self._bad('gopher://1.2.3.4/x')

    def test_rejects_loopback(self):
        self._bad('http://127.0.0.1/hook')
        self._bad('http://localhost/hook')
        self._bad('http://[::1]/hook')

    def test_rejects_cloud_metadata(self):
        self._bad('http://169.254.169.254/latest/meta-data/')

    def test_rejects_private_ranges(self):
        self._bad('http://10.0.0.5/hook')
        self._bad('http://192.168.1.10/hook')
        self._bad('http://172.16.0.1/hook')

    def test_rejects_empty_or_no_host(self):
        self._bad('http:///hook')
        self._bad('not-a-url')

    def test_accepts_public_ip_literal(self):
        # IP público (sem depender de DNS no teste).
        self.assertEqual(
            validate_public_webhook_url('https://93.184.216.34/hook'),
            'https://93.184.216.34/hook',
        )
