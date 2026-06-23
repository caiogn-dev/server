import hmac
import hashlib
import logging
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from apps.postado.models import PostadoClient, PostadoPack
from apps.postado.api.serializers import PostadoClientCreateSerializer
from apps.postado.tasks import generate_pack

logger = logging.getLogger(__name__)


class PostadoSignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = PostadoClientCreateSerializer(data=request.data)
        if ser.is_valid():
            client = ser.save()
            return Response({'id': str(client.id), 'status': 'created'}, status=status.HTTP_201_CREATED)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)


class PostadoMPWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not self._validate_signature(request):
            logger.warning("PostadoMPWebhook: assinatura inválida ou ausente — rejeitando request")
            return Response({'status': 'invalid_signature'}, status=status.HTTP_403_FORBIDDEN)

        preapproval_id = request.query_params.get('preapproval_id', '')
        payload = request.data

        action = payload.get('action', '')
        if action not in ('payment.created', 'payment.updated'):
            return Response({'status': 'ignored'})

        if not preapproval_id:
            return Response({'status': 'no_subscription'}, status=400)

        client_obj = PostadoClient.objects.filter(mp_subscription_id=preapproval_id).first()
        if not client_obj:
            logger.warning("MP webhook: no client for preapproval_id=%s", preapproval_id)
            return Response({'status': 'client_not_found'}, status=200)

        month = timezone.now().strftime('%Y-%m')
        pack, created = PostadoPack.objects.get_or_create(
            client=client_obj,
            month=month,
        )
        if created:
            generate_pack.delay(str(pack.id))
            logger.info("Triggered generate_pack for client %s month %s", client_obj.business_name, month)

        return Response({'status': 'ok'})

    def _validate_signature(self, request) -> bool:
        """
        Validate Mercado Pago webhook signature.

        MP sends: x-signature: ts=<timestamp>,v1=<hmac_sha256>
        Signed message template: id:<data_id>;request-id:<x-request-id>;ts:<timestamp>;

        Falls back to body HMAC when MP's structured header is absent.
        Returns True when no secret is configured (fail-open with warning).
        """
        webhook_secret = getattr(settings, 'POSTADO_MP_WEBHOOK_SECRET', '')
        if not webhook_secret:
            logger.warning("PostadoMPWebhook: POSTADO_MP_WEBHOOK_SECRET não configurado — validação ignorada")
            return True

        x_signature = request.headers.get('X-Signature', '')

        # Try Mercado Pago's structured signature format: ts=<ts>,v1=<hash>
        if x_signature and ',' in x_signature:
            ts = ''
            v1 = ''
            for part in x_signature.split(','):
                key, _, val = part.partition('=')
                if key.strip() == 'ts':
                    ts = val.strip()
                elif key.strip() == 'v1':
                    v1 = val.strip()

            data_id = (
                request.query_params.get('data.id')
                or (request.data.get('data', {}) or {}).get('id', '')
                if hasattr(request.data, 'get') else ''
            )
            x_request_id = request.headers.get('X-Request-Id', '')

            if ts and v1:
                manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
                expected = hmac.new(
                    webhook_secret.encode(),
                    manifest.encode(),
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(v1, expected):
                    return True
                logger.warning("PostadoMPWebhook: falha na verificação da assinatura estruturada MP")
                return False

        # Fallback: plain HMAC-SHA256 over raw body (for simpler MP integrations)
        provided_sig = (
            x_signature
            or request.query_params.get('signature', '')
            or request.headers.get('X-Hub-Signature', '')
        )
        if not provided_sig:
            logger.warning("PostadoMPWebhook: x-signature ausente")
            return False

        # Strip algorithm prefix (e.g. "sha256=abc...")
        if '=' in provided_sig and len(provided_sig) < 20:
            provided_sig = provided_sig.split('=', 1)[-1]

        try:
            body = request.body
            expected = hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(provided_sig, expected):
                return True
            logger.warning("PostadoMPWebhook: falha na verificação do HMAC de corpo")
            return False
        except Exception as e:
            logger.error("PostadoMPWebhook: erro ao calcular HMAC: %s", e)
            return False
