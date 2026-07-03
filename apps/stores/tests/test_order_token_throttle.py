"""
Testes de rate limiting para endpoints públicos de pedido por token.

Endpoints cobertos:
  GET /api/v1/mobile/orders/by-token/{token}/        → OrderByTokenView
  GET /api/v1/mobile/orders/{id}/payment-status/     → PaymentStatusView

Ambos são AllowAny e protegem os dados do pedido (incluindo PIX/endereço)
apenas com o access_token — devem ter limite mais restritivo que o anon padrão.

Todos os testes usam SimpleTestCase (sem banco de dados) para compatibilidade
com o container de CI onde SQLite não suporta `add_index concurrently`.
"""
import uuid
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle


FAST_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "order-token-throttle-test",
    }
}

# override_settings não atualiza SimpleRateThrottle.THROTTLE_RATES (snapshot de import-time).
# Usamos patch.dict diretamente para forçar rate baixa nos testes funcionais.
RATE_1_PER_MIN = {"order_token": "1/minute"}


class OrderTokenThrottleConfigTest(SimpleTestCase):
    """Verifica que a configuração de rate limit está presente e com o valor correto."""

    def test_order_token_rate_definida_no_settings(self):
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("order_token", rates, "Falta a rate 'order_token' em DEFAULT_THROTTLE_RATES")
        self.assertEqual(rates["order_token"], "30/minute")

    def test_order_by_token_view_usa_throttle_dedicado(self):
        from apps.stores.api.webhooks import OrderByTokenView, _OrderTokenThrottle

        throttle_classes = OrderByTokenView.throttle_classes
        self.assertTrue(
            any(issubclass(t, _OrderTokenThrottle) or t is _OrderTokenThrottle for t in throttle_classes),
            f"OrderByTokenView.throttle_classes deve incluir _OrderTokenThrottle, mas é {throttle_classes}",
        )

    def test_payment_status_view_usa_throttle_dedicado(self):
        from apps.stores.api.webhooks import PaymentStatusView, _OrderTokenThrottle

        throttle_classes = PaymentStatusView.throttle_classes
        self.assertTrue(
            any(issubclass(t, _OrderTokenThrottle) or t is _OrderTokenThrottle for t in throttle_classes),
            f"PaymentStatusView.throttle_classes deve incluir _OrderTokenThrottle, mas é {throttle_classes}",
        )

    def test_order_token_throttle_scope(self):
        from apps.stores.api.webhooks import _OrderTokenThrottle

        self.assertEqual(_OrderTokenThrottle.scope, "order_token")

    def test_order_token_throttle_herda_de_anon_rate_throttle(self):
        from rest_framework.throttling import AnonRateThrottle
        from apps.stores.api.webhooks import _OrderTokenThrottle

        self.assertTrue(
            issubclass(_OrderTokenThrottle, AnonRateThrottle),
            "_OrderTokenThrottle deve herdar de AnonRateThrottle para chaveamento por IP",
        )


def _make_request_factory_request(factory, path, ip="10.0.0.1"):
    """Cria GET request via APIRequestFactory com REMOTE_ADDR fixo para o throttle."""
    req = factory.get(path)
    req.META["REMOTE_ADDR"] = ip
    return req


class OrderTokenThrottleFunctionalTest(SimpleTestCase):
    """
    Testa que o throttle de fato dispara 429 quando o limite é atingido.

    Usa patch.dict(SimpleRateThrottle.THROTTLE_RATES) para forçar rate=1/min
    sem depender de override_settings (que não atualiza o snapshot de import-time).
    APIRequestFactory + mock do ORM para não precisar de Redis ou banco.
    """

    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    def tearDown(self):
        cache.clear()

    # -- OrderByTokenView --

    def test_primeira_requisicao_by_token_nao_e_throttled(self):
        """Primeira request com token inválido → 404, nunca 429."""
        from apps.stores.models import StoreOrder
        from apps.stores.api.webhooks import OrderByTokenView

        view = OrderByTokenView.as_view()
        req = _make_request_factory_request(self.factory, "/api/v1/mobile/orders/by-token/x/")

        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, RATE_1_PER_MIN):
            with patch.object(
                StoreOrder.objects, "select_related",
                return_value=MagicMock(prefetch_related=MagicMock(return_value=MagicMock(
                    get=MagicMock(side_effect=StoreOrder.DoesNotExist)
                ))),
            ):
                resp = view(req, access_token="token-invalido-xyz")

        self.assertNotEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_segunda_requisicao_by_token_e_throttled(self):
        """Com rate=1/min, a segunda request do mesmo IP deve retornar 429."""
        from apps.stores.models import StoreOrder
        from apps.stores.api.webhooks import OrderByTokenView

        view = OrderByTokenView.as_view()
        not_found_qs = MagicMock(prefetch_related=MagicMock(return_value=MagicMock(
            get=MagicMock(side_effect=StoreOrder.DoesNotExist)
        )))

        def make_req():
            return _make_request_factory_request(self.factory, "/api/v1/mobile/orders/by-token/x/")

        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, RATE_1_PER_MIN):
            with patch.object(StoreOrder.objects, "select_related", return_value=not_found_qs):
                view(make_req(), access_token="token-invalido-xyz")  # primeira
            resp = view(make_req(), access_token="token-invalido-xyz")  # segunda — só throttle

        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # -- PaymentStatusView --

    def test_primeira_requisicao_payment_status_nao_e_throttled(self):
        """Primeira request com UUID inexistente → não é 429."""
        from apps.stores.models import StoreOrder
        from apps.stores.api.webhooks import PaymentStatusView

        view = PaymentStatusView.as_view()
        order_id = uuid.uuid4()
        req = _make_request_factory_request(
            self.factory, f"/api/v1/mobile/orders/{order_id}/payment-status/"
        )

        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, RATE_1_PER_MIN):
            with patch.object(
                StoreOrder.objects, "select_related",
                return_value=MagicMock(prefetch_related=MagicMock(return_value=MagicMock(
                    get=MagicMock(side_effect=StoreOrder.DoesNotExist)
                ))),
            ):
                resp = view(req, order_id=order_id)

        self.assertNotEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_segunda_requisicao_payment_status_e_throttled(self):
        """Com rate=1/min, a segunda request do mesmo IP deve retornar 429."""
        from apps.stores.models import StoreOrder
        from apps.stores.api.webhooks import PaymentStatusView

        view = PaymentStatusView.as_view()
        order_id = uuid.uuid4()
        not_found_qs = MagicMock(prefetch_related=MagicMock(return_value=MagicMock(
            get=MagicMock(side_effect=StoreOrder.DoesNotExist)
        )))

        def make_req():
            return _make_request_factory_request(
                self.factory, f"/api/v1/mobile/orders/{order_id}/payment-status/"
            )

        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, RATE_1_PER_MIN):
            with patch.object(StoreOrder.objects, "select_related", return_value=not_found_qs):
                view(make_req(), order_id=order_id)  # primeira
            resp = view(make_req(), order_id=order_id)  # segunda — só throttle

        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
