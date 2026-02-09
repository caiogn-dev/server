"""
Handover Protocol - Backend Django

Este módulo implementa o protocolo de transferência entre Bot e Atendimento Humano.

Endpoints:
- POST /api/v1/conversations/<id>/handover/bot/     -> Transferir para Bot
- POST /api/v1/conversations/<id>/handover/human/   -> Transferir para Humano  
- GET  /api/v1/conversations/<id>/handover/status/  -> Ver status atual
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json

User = get_user_model()


class HandoverStatus(models.TextChoices):
    BOT = 'bot', 'Bot'
    HUMAN = 'human', 'Human'
    PENDING = 'pending', 'Pendente'


class HandoverRequestStatus(models.TextChoices):
    PENDING = 'pending', 'Pendente'
    APPROVED = 'approved', 'Aprovado'
    REJECTED = 'rejected', 'Rejeitado'
    EXPIRED = 'expired', 'Expirado'


class ConversationHandover(models.Model):
    """
    Modelo para controle de handover de uma conversa.
    """
    conversation = models.OneToOneField(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='handover',
        verbose_name='Conversa'
    )
    status = models.CharField(
        max_length=20,
        choices=HandoverStatus.choices,
        default=HandoverStatus.BOT,
        verbose_name='Status'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_conversations',
        verbose_name='Atribuído a'
    )
    last_transfer_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Última transferência'
    )
    last_transfer_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfers_made',
        verbose_name='Transferido por'
    )
    transfer_reason = models.TextField(
        blank=True,
        verbose_name='Motivo da transferência'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Controle de Handover'
        verbose_name_plural = 'Controles de Handover'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.conversation} - {self.get_status_display()}"

    def transfer_to_bot(self, user=None, reason=None):
        """Transfere a conversa para o bot."""
        self.status = HandoverStatus.BOT
        self.assigned_to = None
        self.last_transfer_at = timezone.now()
        self.last_transfer_by = user
        self.transfer_reason = reason or ''
        self.save()
        
        # Notificar via WebSocket
        notify_handover_update(self)
        
        # Criar log
        HandoverLog.objects.create(
            conversation=self.conversation,
            from_status=HandoverStatus.HUMAN,
            to_status=HandoverStatus.BOT,
            performed_by=user,
            reason=reason
        )
        
        return self

    def transfer_to_human(self, user=None, assigned_to=None, reason=None):
        """Transfere a conversa para atendimento humano."""
        previous_status = self.status
        self.status = HandoverStatus.HUMAN
        self.assigned_to = assigned_to or user
        self.last_transfer_at = timezone.now()
        self.last_transfer_by = user
        self.transfer_reason = reason or ''
        self.save()
        
        # Notificar via WebSocket
        notify_handover_update(self)
        
        # Criar log
        HandoverLog.objects.create(
            conversation=self.conversation,
            from_status=previous_status,
            to_status=HandoverStatus.HUMAN,
            performed_by=user,
            assigned_to=assigned_to,
            reason=reason
        )
        
        return self


class HandoverRequest(models.Model):
    """
    Modelo para solicitações de handover (bot solicita transferência).
    """
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='handover_requests',
        verbose_name='Conversa'
    )
    status = models.CharField(
        max_length=20,
        choices=HandoverRequestStatus.choices,
        default=HandoverRequestStatus.PENDING,
        verbose_name='Status'
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_requests_made',
        verbose_name='Solicitado por'
    )
    reason = models.TextField(
        blank=True,
        verbose_name='Motivo'
    )
    priority = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Baixa'),
            ('medium', 'Média'),
            ('high', 'Alta'),
            ('urgent', 'Urgente'),
        ],
        default='medium',
        verbose_name='Prioridade'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_requests_approved',
        verbose_name='Aprovado por'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Aprovado em'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_requests_assigned',
        verbose_name='Atribuído a'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Expira em'
    )

    class Meta:
        verbose_name = 'Solicitação de Handover'
        verbose_name_plural = 'Solicitações de Handover'
        ordering = ['-created_at']

    def __str__(self):
        return f"Solicitação {self.id} - {self.get_status_display()}"

    def approve(self, user, assigned_to=None):
        """Aprova a solicitação de handover."""
        self.status = HandoverRequestStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.assigned_to = assigned_to
        self.save()
        
        # Transferir a conversa
        handover, _ = ConversationHandover.objects.get_or_create(
            conversation=self.conversation,
            defaults={'status': HandoverStatus.BOT}
        )
        handover.transfer_to_human(
            user=user,
            assigned_to=assigned_to,
            reason=self.reason
        )
        
        return self

    def reject(self, user):
        """Rejeita a solicitação de handover."""
        self.status = HandoverRequestStatus.REJECTED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()
        return self


class HandoverLog(models.Model):
    """
    Log de todas as transferências realizadas.
    """
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='handover_logs',
        verbose_name='Conversa'
    )
    from_status = models.CharField(
        max_length=20,
        choices=HandoverStatus.choices,
        verbose_name='De'
    )
    to_status = models.CharField(
        max_length=20,
        choices=HandoverStatus.choices,
        verbose_name='Para'
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_logs',
        verbose_name='Realizado por'
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_logs_assigned',
        verbose_name='Atribuído a'
    )
    reason = models.TextField(
        blank=True,
        verbose_name='Motivo'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de Handover'
        verbose_name_plural = 'Logs de Handover'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.conversation} - {self.from_status} → {self.to_status}"


def notify_handover_update(handover):
    """
    Notifica via WebSocket sobre atualização de handover.
    """
    channel_layer = get_channel_layer()
    
    # Notificar no grupo da conversa
    async_to_sync(channel_layer.group_send)(
        f"conversation_{handover.conversation.id}",
        {
            "type": "handover_updated",
            "conversation_id": str(handover.conversation.id),
            "handover_status": handover.status,
            "assigned_to": str(handover.assigned_to.id) if handover.assigned_to else None,
            "assigned_to_name": handover.assigned_to.get_full_name() if handover.assigned_to else None,
            "timestamp": handover.last_transfer_at.isoformat() if handover.last_transfer_at else None,
        }
    )
    
    # Notificar no grupo da loja (para operadores)
    if hasattr(handover.conversation, 'store') and handover.conversation.store:
        async_to_sync(channel_layer.group_send)(
            f"store_{handover.conversation.store.id}_operators",
            {
                "type": "handover_updated",
                "conversation_id": str(handover.conversation.id),
                "handover_status": handover.status,
                "assigned_to": str(handover.assigned_to.id) if handover.assigned_to else None,
                "assigned_to_name": handover.assigned_to.get_full_name() if handover.assigned_to else None,
            }
        )
