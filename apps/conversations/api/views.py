"""
Conversation API views.
"""
import logging
from django.utils import timezone
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
        ).update(status='read', read_at=timezone.now())
        
        # Mark Instagram messages as read
        # InstagramMessage usa 'is_from_business' em vez de 'direction'
        InstagramMessage.objects.filter(
            conversation_id=conversation.id,
            is_from_business=False,  # Mensagens do cliente (inbound)
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        
        # Refresh conversation to update unread_count
        conversation.refresh_from_db()
        
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Get conversation messages",
        description="Returns all messages for this conversation from WhatsApp, Instagram, and Messenger",
        responses={200: dict}
    )
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get all messages for the conversation."""
        conversation = self.get_object()
        
        # Get messages from different sources
        from apps.whatsapp.models import Message as WhatsAppMessage
        from apps.instagram.models import InstagramMessage
        
        messages_list = []
        
        # Get WhatsApp messages
        try:
            wa_messages = WhatsAppMessage.objects.filter(
                conversation_id=conversation.id
            ).order_by('created_at')
            for msg in wa_messages:
                messages_list.append({
                    'id': str(msg.id),
                    'whatsapp_message_id': msg.whatsapp_message_id,
                    'conversation_id': str(conversation.id),
                    'direction': msg.direction,
                    'message_type': msg.message_type,
                    'status': msg.status,
                    'from_number': msg.from_number,
                    'to_number': msg.to_number,
                    'text_body': msg.text_body,
                    'content': msg.content,
                    'media_url': msg.media_url,
                    'media_mime_type': msg.media_mime_type,
                    'created_at': msg.created_at.isoformat() if msg.created_at else None,
                    'sent_at': msg.sent_at.isoformat() if msg.sent_at else None,
                    'delivered_at': msg.delivered_at.isoformat() if msg.delivered_at else None,
                    'read_at': msg.read_at.isoformat() if msg.read_at else None,
                    'error_message': msg.error_message,
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'account': str(msg.account.id) if msg.account else None,
                    'updated_at': msg.updated_at.isoformat() if msg.updated_at else None,
                })
        except Exception as e:
            logger.error(f"Error fetching WhatsApp messages: {e}")
        
        # Get Instagram messages
        try:
            ig_messages = InstagramMessage.objects.filter(
                conversation_id=conversation.id
            ).order_by('created_at')
            for msg in ig_messages:
                messages_list.append({
                    'id': str(msg.id),
                    'whatsapp_message_id': msg.instagram_message_id or '',
                    'conversation_id': str(conversation.id),
                    'direction': 'outbound' if msg.is_from_business else 'inbound',
                    'message_type': msg.message_type or 'text',
                    'status': 'read' if msg.is_read else 'sent',
                    'from_number': msg.sender_id or '',
                    'to_number': msg.recipient_id or '',
                    'text_body': msg.text or '',
                    'content': msg.text or '',
                    'media_url': msg.media_url,
                    'media_mime_type': None,
                    'created_at': msg.created_at.isoformat() if msg.created_at else None,
                    'sent_at': msg.sent_at.isoformat() if msg.sent_at else None,
                    'delivered_at': None,
                    'read_at': msg.read_at.isoformat() if msg.read_at else None,
                    'error_message': msg.error_message,
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'account': str(msg.account.id) if msg.account else None,
                    'updated_at': msg.updated_at.isoformat() if msg.updated_at else None,
                })
        except Exception as e:
            logger.error(f"Error fetching Instagram messages: {e}")
        
        # Sort messages by created_at
        messages_list.sort(key=lambda x: x['created_at'] or '')
        
        return Response(messages_list)

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
