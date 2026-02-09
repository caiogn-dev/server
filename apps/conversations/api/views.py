"""
Conversation API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from ..models import Conversation, ConversationNote
from ..services import ConversationService
from .serializers import (
    ConversationSerializer,
    ConversationNoteSerializer,
    SwitchModeSerializer,
    AddNoteSerializer,
    UpdateContextSerializer,
    TagSerializer,
    AssignAgentSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


@extend_schema_view(
    list=extend_schema(summary="List conversations"),
    retrieve=extend_schema(summary="Get conversation details"),
)
class ConversationViewSet(viewsets.ModelViewSet):
    """ViewSet for Conversation management."""
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'mode', 'assigned_agent']

    def get_queryset(self):
        return Conversation.objects.select_related(
            'account', 'assigned_agent'
        ).filter(is_active=True)

    @extend_schema(
        summary="Switch to human mode",
        request=SwitchModeSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def switch_to_human(self, request, pk=None):
        """Switch conversation to human mode."""
        serializer = SwitchModeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        agent = None
        
        agent_id = serializer.validated_data.get('agent_id')
        if agent_id:
            try:
                agent = User.objects.get(id=agent_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'Agent not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        conversation = service.switch_to_human(str(pk), agent)
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Switch to auto mode",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def switch_to_auto(self, request, pk=None):
        """Switch conversation to auto mode."""
        service = ConversationService()
        conversation = service.switch_to_auto(str(pk))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Assign agent",
        request=AssignAgentSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def assign_agent(self, request, pk=None):
        """Assign an agent to the conversation."""
        serializer = AssignAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            agent = User.objects.get(id=serializer.validated_data['agent_id'])
        except User.DoesNotExist:
            return Response(
                {'error': 'Agent not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        service = ConversationService()
        conversation = service.assign_agent(str(pk), agent)
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Unassign agent",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def unassign_agent(self, request, pk=None):
        """Unassign agent from the conversation."""
        service = ConversationService()
        conversation = service.unassign_agent(str(pk))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Close conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close the conversation."""
        service = ConversationService()
        conversation = service.close_conversation(str(pk))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Resolve conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark conversation as resolved."""
        service = ConversationService()
        conversation = service.resolve_conversation(str(pk))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Reopen conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen the conversation."""
        service = ConversationService()
        conversation = service.reopen_conversation(str(pk))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Get conversation notes",
        responses={200: ConversationNoteSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def notes(self, request, pk=None):
        """Get notes for the conversation."""
        service = ConversationService()
        notes = service.get_notes(str(pk))
        return Response(ConversationNoteSerializer(notes, many=True).data)

    @extend_schema(
        summary="Add note to conversation",
        request=AddNoteSerializer,
        responses={201: ConversationNoteSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add a note to the conversation."""
        serializer = AddNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        note = service.add_note(
            str(pk),
            serializer.validated_data['content'],
            request.user
        )
        return Response(
            ConversationNoteSerializer(note).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Update conversation context",
        request=UpdateContextSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def update_context(self, request, pk=None):
        """Update conversation context."""
        serializer = UpdateContextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.update_context(
            str(pk),
            serializer.validated_data['context']
        )
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Add tag to conversation",
        request=TagSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_tag(self, request, pk=None):
        """Add a tag to the conversation."""
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.add_tag(str(pk), serializer.validated_data['tag'])
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Remove tag from conversation",
        request=TagSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def remove_tag(self, request, pk=None):
        """Remove a tag from the conversation."""
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.remove_tag(str(pk), serializer.validated_data['tag'])
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Mark conversation as read",
        description="Marks all unread messages in this conversation as read",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark all messages in conversation as read."""
        conversation = self.get_object()
        
        # Update all unread inbound messages in this conversation
        from apps.whatsapp.models import Message as WhatsAppMessage
        from apps.instagram.models import InstagramMessage
        
        # Mark WhatsApp messages as read
        WhatsAppMessage.objects.filter(
            conversation_id=conversation.id,
            direction='inbound',
            status__in=['delivered', 'sent']
        ).update(status='read')
        
        # Mark Instagram messages as read
        InstagramMessage.objects.filter(
            conversation_id=conversation.id,
            direction='inbound',
            status__in=['delivered', 'sent']
        ).update(status='read')
        
        # Refresh conversation to update unread_count
        conversation.refresh_from_db()
        
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Get conversation statistics",
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get conversation statistics."""
        account_id = request.query_params.get('account_id')
        
        if not account_id:
            return Response(
                {'error': 'account_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ConversationService()
        stats = service.get_conversation_stats(account_id)
        return Response(stats)
