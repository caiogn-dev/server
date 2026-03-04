""" Marketing v2 - Views. """
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Campaign, Template, Automation, ScheduledMessage
from .serializers import (
    CampaignSerializer, TemplateSerializer,
    AutomationSerializer, ScheduledMessageSerializer
)
from .tasks import execute_automation, process_scheduled_messages


class CampaignViewSet(viewsets.ModelViewSet):
    """Gerenciar campanhas de marketing."""
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'channel', 'store']

    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Agendar campanha."""
        campaign = self.get_object()
        from django.utils import timezone
        campaign.status = Campaign.Status.SCHEDULED
        campaign.scheduled_at = request.data.get('scheduled_at') or timezone.now()
        campaign.save(update_fields=['status', 'scheduled_at'])
        return Response({'status': 'scheduled'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancelar campanha."""
        campaign = self.get_object()
        campaign.status = Campaign.Status.CANCELLED
        campaign.save(update_fields=['status'])
        return Response({'status': 'cancelled'})


class TemplateViewSet(viewsets.ModelViewSet):
    """Gerenciar templates."""
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['channel', 'whatsapp_status']


class AutomationViewSet(viewsets.ModelViewSet):
    """Gerenciar automações."""
    queryset = Automation.objects.all()
    serializer_class = AutomationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['trigger', 'is_active']

    @action(detail=True, methods=['post'])
    def trigger(self, request, pk=None):
        """Disparar automação manualmente."""
        automation = self.get_object()
        result = execute_automation.delay(str(automation.id), request.data)
        return Response({'task_id': result.id, 'status': 'triggered'})

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Ativar/desativar automação."""
        automation = self.get_object()
        automation.is_active = not automation.is_active
        automation.save(update_fields=['is_active'])
        return Response({'is_active': automation.is_active})


class ScheduledMessageViewSet(viewsets.ModelViewSet):
    """Gerenciar mensagens agendadas."""
    queryset = ScheduledMessage.objects.all()
    serializer_class = ScheduledMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'channel', 'store']

    @action(detail=False, methods=['post'])
    def process_pending(self, request):
        """Processar mensagens pendentes agora."""
        result = process_scheduled_messages.delay()
        return Response({'task_id': result.id, 'status': 'processing'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancelar mensagem agendada."""
        message = self.get_object()
        message.status = ScheduledMessage.Status.CANCELLED
        message.save(update_fields=['status'])
        return Response({'status': 'cancelled'})
