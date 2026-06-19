import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from apps.postado.models import PostadoClient, PostadoPack
from apps.postado.api.serializers import PostadoClientCreateSerializer
from apps.postado.tasks import generate_pack
from apps.webhooks.handlers.mercadopago_handler import _verify_mercadopago_signature

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
        payload = request.data or {}

        # Verifica assinatura HMAC do Mercado Pago — sem isso qualquer um forja
        # "pagamento" e dispara generate_pack (geração de conteúdo não paga).
        if not _verify_mercadopago_signature(request, payload):
            logger.warning("Postado MP webhook: assinatura inválida — rejeitado")
            return Response({'status': 'invalid_signature'}, status=403)

        preapproval_id = request.query_params.get('preapproval_id', '')

        action = payload.get('action', '')
        if action not in ('payment.created', 'payment.updated'):
            return Response({'status': 'ignored'})

        if not preapproval_id:
            return Response({'status': 'no_subscription'}, status=400)

        client_obj = PostadoClient.objects.filter(mp_subscription_id=preapproval_id).first()
        if not client_obj:
            logger.warning(f"MP webhook: no client for preapproval_id={preapproval_id}")
            return Response({'status': 'client_not_found'}, status=200)

        month = timezone.now().strftime('%Y-%m')
        pack, created = PostadoPack.objects.get_or_create(
            client=client_obj,
            month=month,
        )
        if created:
            generate_pack.delay(str(pack.id))
            logger.info(f"Triggered generate_pack for client {client_obj.business_name} month {month}")

        return Response({'status': 'ok'})
