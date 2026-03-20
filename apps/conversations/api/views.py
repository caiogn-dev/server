"""
Conversation API views.
"""
import logging
from django.utils import timezone
from django.db.models import Q
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


def _accessible_conversations(user):
    queryset = Conversation.objects.select_related(
        'account', 'assigned_agent'
    ).prefetch_related(
        'account__stores', 'account__company_profile'
    )
    if user.is_superuser or user.is_staff:
        # Admins see all conversations regardless of is_active status
        return queryset

    # Regular users only see conversations they can access
    return queryset.filter(
        is_active=True
    ).filter(
        Q(account__owner=user) |
        Q(account__stores__owner=user) |
        Q(account__stores__staff=user) |
        Q(account__company_profile__store__owner=user) |
        Q(account__company_profile__store__staff=user)
    ).distinct()


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
        return _accessible_conversations(self.request.user)

    @extend_schema(
        summary="Switch to human mode",
        request=SwitchModeSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def switch_to_human(self, request, pk=None):
        """Switch conversation to human mode."""
        conversation = self.get_object()
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
        
        conversation = service.switch_to_human(str(conversation.id), agent)
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Switch to auto mode",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def switch_to_auto(self, request, pk=None):
        """Switch conversation to auto mode."""
        conversation = self.get_object()
        service = ConversationService()
        conversation = service.switch_to_auto(str(conversation.id))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Assign agent",
        request=AssignAgentSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def assign_agent(self, request, pk=None):
        """Assign an agent to the conversation."""
        conversation = self.get_object()
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
        conversation = service.assign_agent(str(conversation.id), agent)
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Unassign agent",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def unassign_agent(self, request, pk=None):
        """Unassign agent from the conversation."""
        conversation = self.get_object()
        service = ConversationService()
        conversation = service.unassign_agent(str(conversation.id))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Close conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close the conversation."""
        conversation = self.get_object()
        service = ConversationService()
        conversation = service.close_conversation(str(conversation.id))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Resolve conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark conversation as resolved."""
        conversation = self.get_object()
        service = ConversationService()
        conversation = service.resolve_conversation(str(conversation.id))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Reopen conversation",
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen the conversation."""
        conversation = self.get_object()
        service = ConversationService()
        conversation = service.reopen_conversation(str(conversation.id))
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Get conversation notes",
        responses={200: ConversationNoteSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def notes(self, request, pk=None):
        """Get notes for the conversation."""
        conversation = self.get_object()
        service = ConversationService()
        notes = service.get_notes(str(conversation.id))
        return Response(ConversationNoteSerializer(notes, many=True).data)

    @extend_schema(
        summary="Add note to conversation",
        request=AddNoteSerializer,
        responses={201: ConversationNoteSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add a note to the conversation."""
        conversation = self.get_object()
        serializer = AddNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        note = service.add_note(
            str(conversation.id),
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
        conversation = self.get_object()
        serializer = UpdateContextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.update_context(
            str(conversation.id),
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
        conversation = self.get_object()
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.add_tag(str(conversation.id), serializer.validated_data['tag'])
        return Response(ConversationSerializer(conversation).data)

    @extend_schema(
        summary="Remove tag from conversation",
        request=TagSerializer,
        responses={200: ConversationSerializer}
    )
    @action(detail=True, methods=['post'])
    def remove_tag(self, request, pk=None):
        """Remove a tag from the conversation."""
        conversation = self.get_object()
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = ConversationService()
        conversation = service.remove_tag(str(conversation.id), serializer.validated_data['tag'])
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
        
        # Enforce account ownership/access
        from apps.whatsapp.models import WhatsAppAccount
        account_exists = WhatsAppAccount.objects.filter(id=account_id).exists()
        if not account_exists:
            return Response(
                {'error': 'account not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not (request.user.is_superuser or request.user.is_staff):
            has_access = WhatsAppAccount.objects.filter(
                id=account_id
            ).filter(
                Q(owner=request.user) |
                Q(stores__owner=request.user) |
                Q(stores__staff=request.user) |
                Q(company_profile__store__owner=request.user) |
                Q(company_profile__store__staff=request.user)
            ).exists()
            if not has_access:
                return Response(
                    {'error': 'forbidden'},
                    status=status.HTTP_403_FORBIDDEN
                )

        service = ConversationService()
        stats = service.get_conversation_stats(account_id)
        return Response(stats)
