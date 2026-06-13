"""LGPD compliance endpoints for user data management."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import logging

from apps.core.services.customer_identity import CustomerIdentityService

logger = logging.getLogger(__name__)


class LGPDViewSet(viewsets.ViewSet):
    """LGPD compliance endpoints (art. 18 — direitos do titular)."""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def data_export(self, request):
        """Exporta os dados pessoais do titular (acesso/portabilidade — art. 18)."""
        user = request.user
        logger.info("LGPD: data export requested (user_id=%s)", user.id)

        # Pedidos do titular (sem PII de terceiros)
        orders = []
        try:
            from apps.stores.models import StoreOrder
            for o in StoreOrder.objects.filter(customer=user).order_by('-created_at')[:200]:
                orders.append({
                    'order_number': o.order_number,
                    'status': o.status,
                    'total': str(o.total),
                    'created_at': o.created_at.isoformat(),
                })
        except Exception:
            logger.warning("LGPD export: falha ao coletar pedidos", exc_info=True)

        return Response({
            'user': {
                'id': str(user.id),
                'email': user.email,
                'name': user.get_full_name(),
                'joined_at': user.date_joined.isoformat(),
            },
            'orders': orders,
            'timestamp': timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def request_deletion(self, request):
        """Direito ao esquecimento (art. 18, VI): anonimiza os dados do titular."""
        user = request.user
        logger.warning("LGPD: deletion/anonymization requested (user_id=%s)", user.id)
        CustomerIdentityService.anonymize_user(user)
        return Response({
            'status': 'anonymized',
            'message': 'Seus dados pessoais foram anonimizados. O histórico de pedidos '
                       'é mantido de forma não identificável conforme a LGPD.',
            'timestamp': timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)
