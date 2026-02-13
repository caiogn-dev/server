"""
Serializers para Handover Protocol
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    ConversationHandover,
    HandoverRequest,
    HandoverLog,
    HandoverStatus,
    HandoverRequestStatus,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer simplificado para usuário."""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


class ConversationHandoverSerializer(serializers.ModelSerializer):
    """Serializer para estado atual de handover."""
    
    assigned_to = UserSerializer(read_only=True)
    last_transfer_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = ConversationHandover
        fields = [
            'id',
            'conversation',
            'status',
            'status_display',
            'assigned_to',
            'last_transfer_at',
            'last_transfer_by',
            'transfer_reason',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class HandoverRequestSerializer(serializers.ModelSerializer):
    """Serializer para solicitações de handover."""
    
    requested_by = UserSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    
    class Meta:
        model = HandoverRequest
        fields = [
            'id',
            'conversation',
            'status',
            'status_display',
            'requested_by',
            'reason',
            'priority',
            'priority_display',
            'approved_by',
            'approved_at',
            'assigned_to',
            'created_at',
            'expires_at',
        ]
        read_only_fields = [
            'requested_by', 'approved_by', 'approved_at', 
            'assigned_to', 'created_at'
        ]


class CreateHandoverRequestSerializer(serializers.Serializer):
    """Serializer para criar solicitação de handover."""
    
    reason = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        choices=['low', 'medium', 'high', 'urgent'],
        default='medium'
    )


class ApproveHandoverRequestSerializer(serializers.Serializer):
    """Serializer para aprovar solicitação de handover."""
    
    assigned_to_id = serializers.UUIDField(required=False)


class HandoverLogSerializer(serializers.ModelSerializer):
    """Serializer para logs de handover."""
    
    performed_by = UserSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True)
    from_status_display = serializers.CharField(source='get_from_status_display', read_only=True)
    to_status_display = serializers.CharField(source='get_to_status_display', read_only=True)
    
    class Meta:
        model = HandoverLog
        fields = [
            'id',
            'conversation',
            'from_status',
            'from_status_display',
            'to_status',
            'to_status_display',
            'performed_by',
            'assigned_to',
            'reason',
            'created_at',
        ]


class TransferToBotSerializer(serializers.Serializer):
    """Serializer para transferir para bot."""
    
    reason = serializers.CharField(required=False, allow_blank=True)


class TransferToHumanSerializer(serializers.Serializer):
    """Serializer para transferir para humano."""
    
    assigned_to_id = serializers.UUIDField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True)


class HandoverStatusResponseSerializer(serializers.Serializer):
    """Serializer para resposta de status de handover."""
    
    handover_status = serializers.ChoiceField(choices=HandoverStatus.choices)
    status_display = serializers.CharField()
    assigned_to = UserSerializer(required=False)
    assigned_to_name = serializers.CharField(required=False)
    last_transfer_at = serializers.DateTimeField(required=False)
    last_transfer_reason = serializers.CharField(required=False)
