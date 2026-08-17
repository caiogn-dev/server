"""
image_url do catálogo público não pode depender do scheme/host da request.

Bug real: PublicProductSerializer usava request.build_absolute_uri(). Como o
cloudflared termina o TLS no Cloudflare e fala http com o nginx, o Django via
a conexão como http e devolvia image_url em http://backend.pastita.com.br/... —
que o navegador BLOQUEIA como mixed-content numa página https, sumindo a foto.

Agora usa build_absolute_media_url() (settings.BACKEND_URL), independente da
request. Este teste trava isso.
"""
from django.conf import settings
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.core.utils import build_absolute_media_url
from apps.stores.models import StoreProduct
from apps.public_api.serializers import PublicProductSerializer


class ImageUrlSchemeTest(SimpleTestCase):
    def setUp(self):
        # Request "insegura" (http) com host arbitrário — NÃO deve influenciar.
        self.req = APIRequestFactory().get('/', SERVER_NAME='127.0.0.1')

    def test_image_url_ignora_scheme_e_host_da_request(self):
        prod = StoreProduct(name='X', main_image='stores/products/x.webp')
        # Chama o método direto p/ não serializar `variants` (que tocaria o banco).
        ser = PublicProductSerializer(context={'request': self.req})
        out = ser.get_image_url(prod)
        # Sai da base configurada (https em prod), não do host da request.
        self.assertEqual(out, build_absolute_media_url('/media/stores/products/x.webp'))
        self.assertTrue(out.startswith(settings.BACKEND_URL.rstrip('/')))
        self.assertNotIn('127.0.0.1', out)
        self.assertNotIn('testserver', out)

    def test_sem_request_tambem_resolve_absoluto(self):
        prod = StoreProduct(name='Y', main_image='stores/products/y.webp')
        out = PublicProductSerializer(context={}).get_image_url(prod)
        self.assertEqual(out, build_absolute_media_url('/media/stores/products/y.webp'))
