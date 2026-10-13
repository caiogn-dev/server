"""Frete em excesso não pode travar o resto do site para o mesmo IP.

13/10, Cê: um laço no checkout (cardapidex-web 8de9bfb) mandou ~8 cotações de
frete por segundo. Elas contavam no balde GLOBAL do RateLimitMiddleware (100/min
por IP, somando tudo e contando até as recusadas) e no throttle `public_write`
do DRF (o mesmo do carrinho). Resultado: "erro ao adicionar à sacola", perfil e
carteira em 429 — e o restaurante inteiro fica atrás de um IP só.

Agora o frete tem balde próprio nos dois limitadores.
"""
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.core.middleware import RateLimitMiddleware

FRETE = '/api/v1/stores/ce-saladas/delivery-fee/'
SACOLA = '/api/v1/stores/ce-saladas/cart/add/'


def _request(path, ip='10.9.9.9'):
    req = mock.MagicMock()
    req.path = path
    req.method = 'GET'
    req.META = {'REMOTE_ADDR': ip}
    req.headers = {}
    return req


@override_settings(
    RATE_LIMIT_ENABLED=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'frete-sacola'}},
)
class FreteNaoTravaASacolaTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _mw(self):
        from django.conf import settings
        mw = RateLimitMiddleware(lambda request: mock.MagicMock(status_code=200, __setitem__=mock.MagicMock()))
        mw.scoped_limits = settings.RATE_LIMIT_SCOPED_PATHS
        return mw

    def test_rajada_de_frete_nao_bloqueia_a_sacola(self):
        mw = self._mw()
        for _ in range(200):
            mw(_request(FRETE))
        assert mw(_request(SACOLA)).status_code == 200

    def test_frete_tem_limite_proprio(self):
        mw = self._mw()
        codigos = [mw(_request(FRETE)).status_code for _ in range(200)]
        assert 429 in codigos
        assert codigos[0] == 200

    def test_outro_ip_nao_e_afetado(self):
        mw = self._mw()
        for _ in range(200):
            mw(_request(FRETE))
        assert mw(_request(FRETE, ip='10.9.9.10')).status_code == 200


def test_frete_tem_throttle_do_drf_separado_do_carrinho():
    from apps.stores.api.views.storefront_views import PublicWriteThrottle, StoreDeliveryFeeView
    escopos = {t.scope for t in StoreDeliveryFeeView.throttle_classes}
    assert PublicWriteThrottle.scope not in escopos
    assert escopos == {'frete'}
