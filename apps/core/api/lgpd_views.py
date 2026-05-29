"""LGPD compliance endpoints for user data management."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class LGPDViewSet(viewsets.ViewSet):
    """LGPD compliance endpoints."""
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def data_export(self, request):
        """Export all user personal data (DSAR)."""
        user = request.user
        logger.info(f"LGPD: Data export requested by {user.email}")
        return Response({
            'user': {
                'id': str(user.id),
                'email': user.email,
                'name': user.get_full_name(),
                'joined_at': user.date_joined.isoformat(),
            },
            'timestamp': timezone.now().isoformat(),
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def request_deletion(self, request):
        """Request account deletion (right to be forgotten)."""
        user = request.user
        logger.warning(f"LGPD: Deletion requested by {user.email}")
        return Response({
            'status': 'deletion_requested',
            'message': 'Account deletion request registered.',
            'timestamp': timezone.now().isoformat(),
        }, status=status.HTTP_202_ACCEPTED)
