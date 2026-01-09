"""
Notification API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from ..models import Notification, NotificationPreference, PushSubscription
from ..services import NotificationService
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    PushSubscriptionSerializer,
    RegisterPushSubscriptionSerializer,
    MarkReadSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List notifications"),
    retrieve=extend_schema(summary="Get notification details"),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Notification operations."""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['notification_type', 'is_read', 'priority']
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @extend_schema(summary="Get unread count")
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        service = NotificationService()
        count = service.get_unread_count(request.user)
        return Response({'count': count})
    
    @extend_schema(
        summary="Mark notifications as read",
        request=MarkReadSerializer,
        responses={200: dict}
    )
    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        """Mark notifications as read."""
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = NotificationService()
        
        if serializer.validated_data.get('mark_all'):
            count = service.mark_all_as_read(request.user)
            return Response({'marked': count})
        
        notification_ids = serializer.validated_data.get('notification_ids', [])
        marked = 0
        for notification_id in notification_ids:
            if service.mark_as_read(str(notification_id), request.user):
                marked += 1
        
        return Response({'marked': marked})
    
    @extend_schema(summary="Delete notification")
    @action(detail=True, methods=['delete'])
    def remove(self, request, pk=None):
        """Delete a notification."""
        service = NotificationService()
        if service.delete_notification(pk, request.user):
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {'error': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@extend_schema_view(
    retrieve=extend_schema(summary="Get notification preferences"),
    update=extend_schema(summary="Update notification preferences"),
    partial_update=extend_schema(summary="Partial update notification preferences"),
)
class NotificationPreferenceViewSet(viewsets.GenericViewSet):
    """ViewSet for NotificationPreference operations."""
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        service = NotificationService()
        return service.get_or_create_preferences(self.request.user)
    
    @extend_schema(summary="Get preferences")
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's notification preferences."""
        preferences = self.get_object()
        serializer = self.get_serializer(preferences)
        return Response(serializer.data)
    
    @extend_schema(summary="Update preferences")
    @action(detail=False, methods=['put', 'patch'])
    def update_preferences(self, request):
        """Update current user's notification preferences."""
        preferences = self.get_object()
        serializer = self.get_serializer(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List push subscriptions"),
)
class PushSubscriptionViewSet(viewsets.GenericViewSet):
    """ViewSet for PushSubscription operations."""
    serializer_class = PushSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PushSubscription.objects.filter(user=self.request.user, is_active=True)
    
    @extend_schema(summary="List subscriptions")
    def list(self, request):
        """List user's push subscriptions."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Register push subscription",
        request=RegisterPushSubscriptionSerializer,
        responses={201: PushSubscriptionSerializer}
    )
    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register a new push subscription."""
        serializer = RegisterPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = NotificationService()
        subscription = service.register_push_subscription(
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(
            PushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED
        )
    
    @extend_schema(summary="Unregister push subscription")
    @action(detail=False, methods=['post'])
    def unregister(self, request):
        """Unregister a push subscription."""
        endpoint = request.data.get('endpoint')
        if not endpoint:
            return Response(
                {'error': 'endpoint is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = NotificationService()
        if service.unregister_push_subscription(request.user, endpoint):
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        return Response(
            {'error': 'Subscription not found'},
            status=status.HTTP_404_NOT_FOUND
        )
