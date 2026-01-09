"""
Conversation Repository.
"""
from typing import Optional, List
from uuid import UUID
from django.db.models import QuerySet
from django.utils import timezone
from ..models import Conversation, ConversationNote


class ConversationRepository:
    """Repository for Conversation operations."""

    def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get conversation by ID."""
        try:
            return Conversation.objects.select_related('account', 'assigned_agent').get(
                id=conversation_id,
                is_active=True
            )
        except Conversation.DoesNotExist:
            return None

    def get_by_phone_number(
        self,
        account_id: UUID,
        phone_number: str
    ) -> Optional[Conversation]:
        """Get conversation by phone number."""
        try:
            return Conversation.objects.select_related('account', 'assigned_agent').get(
                account_id=account_id,
                phone_number=phone_number,
                is_active=True
            )
        except Conversation.DoesNotExist:
            return None

    def get_or_create(
        self,
        account,
        phone_number: str,
        contact_name: str = ''
    ) -> tuple[Conversation, bool]:
        """Get or create a conversation."""
        return Conversation.objects.get_or_create(
            account=account,
            phone_number=phone_number,
            defaults={
                'contact_name': contact_name,
                'last_message_at': timezone.now(),
            }
        )

    def get_by_account(
        self,
        account_id: UUID,
        status: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 100
    ) -> QuerySet[Conversation]:
        """Get conversations by account."""
        queryset = Conversation.objects.filter(
            account_id=account_id,
            is_active=True
        ).select_related('account', 'assigned_agent')
        
        if status:
            queryset = queryset.filter(status=status)
        if mode:
            queryset = queryset.filter(mode=mode)
        
        return queryset[:limit]

    def get_by_agent(
        self,
        agent_id: int,
        status: Optional[str] = None,
        limit: int = 100
    ) -> QuerySet[Conversation]:
        """Get conversations assigned to an agent."""
        queryset = Conversation.objects.filter(
            assigned_agent_id=agent_id,
            is_active=True
        ).select_related('account')
        
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset[:limit]

    def get_open_conversations(
        self,
        account_id: Optional[UUID] = None,
        limit: int = 100
    ) -> QuerySet[Conversation]:
        """Get open conversations."""
        queryset = Conversation.objects.filter(
            status=Conversation.ConversationStatus.OPEN,
            is_active=True
        ).select_related('account', 'assigned_agent')
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return queryset[:limit]

    def create(self, **kwargs) -> Conversation:
        """Create a new conversation."""
        return Conversation.objects.create(**kwargs)

    def update(self, conversation: Conversation, **kwargs) -> Conversation:
        """Update a conversation."""
        for key, value in kwargs.items():
            setattr(conversation, key, value)
        conversation.save()
        return conversation

    def update_last_message(
        self,
        conversation: Conversation,
        is_customer: bool = True
    ) -> Conversation:
        """Update last message timestamp."""
        now = timezone.now()
        conversation.last_message_at = now
        
        if is_customer:
            conversation.last_customer_message_at = now
        else:
            conversation.last_agent_message_at = now
        
        conversation.save(update_fields=[
            'last_message_at',
            'last_customer_message_at' if is_customer else 'last_agent_message_at',
            'updated_at'
        ])
        return conversation

    def switch_to_human(self, conversation: Conversation, agent=None) -> Conversation:
        """Switch conversation to human mode."""
        conversation.mode = Conversation.ConversationMode.HUMAN
        if agent:
            conversation.assigned_agent = agent
        conversation.save(update_fields=['mode', 'assigned_agent', 'updated_at'])
        return conversation

    def switch_to_auto(self, conversation: Conversation) -> Conversation:
        """Switch conversation to auto mode."""
        conversation.mode = Conversation.ConversationMode.AUTO
        conversation.assigned_agent = None
        conversation.save(update_fields=['mode', 'assigned_agent', 'updated_at'])
        return conversation

    def close(self, conversation: Conversation) -> Conversation:
        """Close a conversation."""
        conversation.status = Conversation.ConversationStatus.CLOSED
        conversation.closed_at = timezone.now()
        conversation.save(update_fields=['status', 'closed_at', 'updated_at'])
        return conversation

    def resolve(self, conversation: Conversation) -> Conversation:
        """Mark conversation as resolved."""
        conversation.status = Conversation.ConversationStatus.RESOLVED
        conversation.resolved_at = timezone.now()
        conversation.save(update_fields=['status', 'resolved_at', 'updated_at'])
        return conversation

    def reopen(self, conversation: Conversation) -> Conversation:
        """Reopen a conversation."""
        conversation.status = Conversation.ConversationStatus.OPEN
        conversation.closed_at = None
        conversation.resolved_at = None
        conversation.save(update_fields=['status', 'closed_at', 'resolved_at', 'updated_at'])
        return conversation

    def add_note(
        self,
        conversation: Conversation,
        content: str,
        author=None
    ) -> ConversationNote:
        """Add a note to a conversation."""
        return ConversationNote.objects.create(
            conversation=conversation,
            author=author,
            content=content
        )

    def get_notes(self, conversation: Conversation) -> QuerySet[ConversationNote]:
        """Get notes for a conversation."""
        return ConversationNote.objects.filter(
            conversation=conversation,
            is_active=True
        ).select_related('author')

    def update_context(
        self,
        conversation: Conversation,
        context: dict
    ) -> Conversation:
        """Update conversation context."""
        conversation.context.update(context)
        conversation.save(update_fields=['context', 'updated_at'])
        return conversation

    def add_tag(self, conversation: Conversation, tag: str) -> Conversation:
        """Add a tag to a conversation."""
        if tag not in conversation.tags:
            conversation.tags.append(tag)
            conversation.save(update_fields=['tags', 'updated_at'])
        return conversation

    def remove_tag(self, conversation: Conversation, tag: str) -> Conversation:
        """Remove a tag from a conversation."""
        if tag in conversation.tags:
            conversation.tags.remove(tag)
            conversation.save(update_fields=['tags', 'updated_at'])
        return conversation
