"""
Regressão de segurança: toca-delivery aceita POST sem assinatura HMAC [P0].

O dispatcher/_verify_signature trata 'toca-delivery' como provider genérico:
retorna None sem verificar a assinatura, permitindo que qualquer atacante
anônimo forje status de entrega (p.ex. 'entregue') para qualquer pedido,
sem nenhuma credencial.

TocaDeliveryHandler.validate_signature() existe mas NUNCA é chamado pelo
dispatcher — código morto.

Correção: adicionar 'toca-delivery' a _PROVIDERS_REQUIRE_SIGNATURE e tratar
o provider no branch elif de _verify_signature (HMAC-SHA256 de request.body
via TOCA_DELIVERY_WEBHOOK_SECRET ou endpoint.secret, comparado ao
X-Toca-Signature).

Técnica: SimpleTestCase + mock request — sem DB/Docker.
"""
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.webhooks.dispatcher import (
    _PROVIDERS_REQUIRE_SIGNATURE,
    WebhookDispatcherView,
)


def _toca_sig(secret: str, body: bytes) -> str:
    """HMAC-SHA256 hex digest — formato esperado pelo TocaDeliveryHandler."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_request(body: bytes, toca_signature: str = None) -> MagicMock:
    """Cria um mock de request com body e headers."""
    req = MagicMock()
    req.body = body
    headers = {}
    if toca_signature is not None:
        headers['X-Toca-Signature'] = toca_signature
    req.headers = headers
    return req


SAMPLE_BODY = json.dumps({
    'corrida_id': '00000000-0000-0000-0000-000000000001',
    'status': 'em_rota',
}).encode()
SAMPLE_PAYLOAD = json.loads(SAMPLE_BODY)


class TocaDeliveryProvidersRequireSignatureTest(SimpleTestCase):
    """Verificação estática: toca-delivery deve estar em _PROVIDERS_REQUIRE_SIGNATURE."""

    def test_toca_delivery_em_providers_require_signature(self):
        self.assertIn(
            'toca-delivery',
            _PROVIDERS_REQUIRE_SIGNATURE,
            "'toca-delivery' não está em _PROVIDERS_REQUIRE_SIGNATURE — "
            "POST sem secret configurado seria aceito (fail-open): "
            "atacante pode forjar qualquer status de entrega.",
        )


class TocaDeliveryVerifySignatureNoEndpointTest(SimpleTestCase):
    """_verify_signature com fallback via TOCA_DELIVERY_WEBHOOK_SECRET (sem WebhookEndpoint)."""

    def _call(self, request, settings_secret=None):
        """Chama _verify_signature com endpoint=None (sem registro no banco)."""
        from apps.webhooks.models import WebhookEndpoint as RealEP
        view = WebhookDispatcherView()
        # Patch só o objects.get para simular "endpoint não encontrado"
        with patch.object(RealEP.objects, 'get', side_effect=RealEP.DoesNotExist):
            if settings_secret is not None:
                with override_settings(TOCA_DELIVERY_WEBHOOK_SECRET=settings_secret):
                    return view._verify_signature(request, 'toca-delivery', SAMPLE_PAYLOAD)
            else:
                with override_settings(TOCA_DELIVERY_WEBHOOK_SECRET=''):
                    return view._verify_signature(request, 'toca-delivery', SAMPLE_PAYLOAD)

    def test_sem_secret_nenhum_retorna_none(self):
        """Sem settings secret → None (dispatcher falha closed por _PROVIDERS_REQUIRE_SIGNATURE)."""
        req = _make_request(SAMPLE_BODY)
        result = self._call(req, settings_secret='')
        self.assertIsNone(
            result,
            "_verify_signature deve retornar None quando TOCA_DELIVERY_WEBHOOK_SECRET "
            "não está configurado (dispatcher fará fail-closed via _PROVIDERS_REQUIRE_SIGNATURE).",
        )

    def test_assinatura_correta_via_settings_retorna_true(self):
        """HMAC correto via settings secret → True."""
        sig = _toca_sig('segredo-settings', SAMPLE_BODY)
        req = _make_request(SAMPLE_BODY, toca_signature=sig)
        result = self._call(req, settings_secret='segredo-settings')
        self.assertTrue(
            result,
            "_verify_signature deve retornar True para assinatura HMAC correta "
            "via TOCA_DELIVERY_WEBHOOK_SECRET.",
        )

    def test_assinatura_errada_via_settings_retorna_false(self):
        """HMAC errado via settings secret → False."""
        req = _make_request(SAMPLE_BODY, toca_signature='deadbeef')
        result = self._call(req, settings_secret='segredo-settings')
        self.assertFalse(
            result,
            "_verify_signature deve retornar False para assinatura inválida.",
        )

    def test_header_ausente_retorna_false(self):
        """X-Toca-Signature ausente → False (não None — assinatura requerida)."""
        req = _make_request(SAMPLE_BODY)  # sem header
        result = self._call(req, settings_secret='segredo-settings')
        self.assertFalse(
            result,
            "_verify_signature deve retornar False quando header X-Toca-Signature "
            "está ausente mas secret está configurado.",
        )


class TocaDeliveryVerifySignatureWithEndpointTest(SimpleTestCase):
    """_verify_signature com WebhookEndpoint configurado no banco."""

    def _call(self, request, endpoint_secret: str, endpoint_sig_header: str = 'X-Toca-Signature'):
        """Chama _verify_signature com endpoint mockado."""
        from apps.webhooks.models import WebhookEndpoint as RealEP
        view = WebhookDispatcherView()
        mock_endpoint = MagicMock(spec=RealEP)
        mock_endpoint.secret = endpoint_secret
        mock_endpoint.signature_header = endpoint_sig_header

        with patch.object(RealEP.objects, 'get', return_value=mock_endpoint):
            return view._verify_signature(request, 'toca-delivery', SAMPLE_PAYLOAD)

    def test_assinatura_correta_via_endpoint_retorna_true(self):
        sig = _toca_sig('db-secret', SAMPLE_BODY)
        req = _make_request(SAMPLE_BODY, toca_signature=sig)
        result = self._call(req, endpoint_secret='db-secret')
        self.assertTrue(
            result,
            "_verify_signature deve retornar True para assinatura correta via endpoint.",
        )

    def test_assinatura_errada_via_endpoint_retorna_false(self):
        req = _make_request(SAMPLE_BODY, toca_signature='wronghex')
        result = self._call(req, endpoint_secret='db-secret')
        self.assertFalse(result)

    def test_header_ausente_via_endpoint_retorna_false(self):
        req = _make_request(SAMPLE_BODY)  # sem X-Toca-Signature
        result = self._call(req, endpoint_secret='db-secret')
        self.assertFalse(
            result,
            "Header X-Toca-Signature ausente com endpoint configurado → False.",
        )
