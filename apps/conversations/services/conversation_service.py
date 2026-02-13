"""
Conversation Service - Business logic for conversation management.
"""
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from django.utils import timezone
from apps.core.exceptions import NotFoundError, ValidationError
from ..models import Conversation, ConversationNote
from ..repositories import ConversationRepository

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for conversation operations."""

    def __init__(self):
        self.repo = ConversationRepository()

    def get_or_create_conversation(
        self,
        account,
        phone_number: str,
        contact_name: str = ''
    ) -> Conversation:
        """Get or create a conversation."""
        conversation, created = self.repo.get_or_create(
            account=account,
            phone_number=phone_number,
            contact_name=contact_name
        )
        
        if created:
            logger.info(f"New conversation created: {conversation.id}")
        else:
            if conversation.status == Conversation.ConversationStatus.CLOSED:
                conversation = self.repo.reopen(conversation)
                logger.info(f"Conversation reopened: {conversation.id}")
        
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation:
        """Get conversation by ID."""
        conversation = self.repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundError(message="Conversation not found")
        return conversation

    def get_conversation_by_phone(
        self,
        account_id: str,
        phone_number: str
    ) -> Optional[Conversation]:
        """Get conversation by phone number."""
        return self.repo.get_by_phone_number(account_id, phone_number)

    def list_conversations(
        self,
        account_id: str,
        status: Optional[str] = None,
        mode: Optional[str] = None,
        limit: int = 100
    ) -> List[Conversation]:
        """List conversations for an account."""
        return list(self.repo.get_by_account(
            account_id=account_id,
            status=status,
            mode=mode,
            limit=limit
        ))

    def list_agent_conversations(
        self,
        agent_id: int,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Conversation]:
        """List conversations assigned to an agent."""
        return list(self.repo.get_by_agent(
            agent_id=agent_id,
            status=status,
            limit=limit
        ))

    def update_last_message(
        self,
        conversation: Conversation,
        is_customer: bool = True
    ) -> Conversation:
        """Update last message timestamp."""
        return self.repo.update_last_message(conversation, is_customer)

    def switch_to_human(
        self,
        conversation_id: str,
        agent=None
    ) -> Conversation:
        """Switch conversation to human mode."""
        conversation = self.get_conversation(conversation_id)
        
        if not conversation.account.human_handoff_enabled:
            raise ValidationError(message="Human handoff is not enabled for this account")
        
        conversation = self.repo.switch_to_human(conversation, agent)
        logger.info(f"Conversation switched to human mode: {conversation.id}")
        
        return conversation

    def switch_to_auto(self, conversation_id: str) -> Conversation:
        """Switch conversation to auto mode."""
        conversation = self.get_conversation(conversation_id)
        conversation = self.repo.switch_to_auto(conversation)
        logger.info(f"Conversation switched to auto mode: {conversation.id}")
        
        return conversation

    def assign_agent(
        self,
        conversation_id: str,
        agent
    ) -> Conversation:
        """Assign an agent to a conversation."""
        conversation = self.get_conversation(conversation_id)
        conversation.assigned_agent = agent
        conversation.save(update_fields=['assigned_agent', 'updated_at'])
        logger.info(f"Agent {agent.id} assigned to conversation: {conversation.id}")
        
        return conversation

    def unassign_agent(self, conversation_id: str) -> Conversation:
        """Unassign agent from a conversation."""
        conversation = self.get_conversation(conversation_id)
        conversation.assigned_agent = None
        conversation.save(update_fields=['assigned_agent', 'updated_at'])
        logger.info(f"Agent unassigned from conversation: {conversation.id}")
        
        return conversation

    def close_conversation(self, conversation_id: str) -> Conversation:
        """Close a conversation."""
        conversation = self.get_conversation(conversation_id)
        conversation = self.repo.close(conversation)
        logger.info(f"Conversation closed: {conversation.id}")
        
        return conversation

    def resolve_conversation(self, conversation_id: str) -> Conversation:
        """Mark conversation as resolved."""
        conversation = self.get_conversation(conversation_id)
        conversation = self.repo.resolve(conversation)
        logger.info(f"Conversation resolved: {conversation.id}")
        
        return conversation

    def reopen_conversation(self, conversation_id: str) -> Conversation:
        """Reopen a conversation."""
        conversation = self.get_conversation(conversation_id)
        conversation = self.repo.reopen(conversation)
        logger.info(f"Conversation reopened: {conversation.id}")
        
        return conversation

    def add_note(
        self,
        conversation_id: str,
        content: str,
        author=None
    ) -> ConversationNote:
        """Add a note to a conversation."""
        conversation = self.get_conversation(conversation_id)
        note = self.repo.add_note(conversation, content, author)
        logger.info(f"Note added to conversation: {conversation.id}")
        
        return note

    def get_notes(self, conversation_id: str) -> List[ConversationNote]:
        """Get notes for a conversation."""
        conversation = self.get_conversation(conversation_id)
        return list(self.repo.get_notes(conversation))

    def update_context(
        self,
        conversation_id: str,
        context: Dict[str, Any]
    ) -> Conversation:
        """Update conversation context."""
        conversation = self.get_conversation(conversation_id)
        return self.repo.update_context(conversation, context)

    def update_contact_name(
        self,
        conversation_id: str,
        contact_name: str
    ) -> Conversation:
        """Update contact name."""
        conversation = self.get_conversation(conversation_id)
        conversation.contact_name = contact_name
        conversation.save(update_fields=['contact_name', 'updated_at'])
        
        return conversation

    def add_tag(self, conversation_id: str, tag: str) -> Conversation:
        """Add a tag to a conversation."""
        conversation = self.get_conversation(conversation_id)
        return self.repo.add_tag(conversation, tag)

    def remove_tag(self, conversation_id: str, tag: str) -> Conversation:
        """Remove a tag from a conversation."""
        conversation = self.get_conversation(conversation_id)
        return self.repo.remove_tag(conversation, tag)

    def set_agent_session(
        self,
        conversation_id: str,
        agent_id: str,
        session_id: str
    ) -> Conversation:
        """Set AI Agent session for a conversation."""
        conversation = self.get_conversation(conversation_id)
        conversation.ai_agent_id = agent_id
        conversation.agent_session_id = session_id
        conversation.save(update_fields=[
            'ai_agent_id', 'agent_session_id', 'updated_at'
        ])
        
        return conversation

    def get_conversation_stats(self, account_id: str) -> Dict[str, Any]:
        """Get conversation statistics for an account."""
        from django.db.models import Count
        
        conversations = Conversation.objects.filter(
            account_id=account_id,
            is_active=True
        )
        
        stats = conversations.values('status').annotate(count=Count('id'))
        mode_stats = conversations.values('mode').annotate(count=Count('id'))
        
        return {
            'total': conversations.count(),
            'by_status': {s['status']: s['count'] for s in stats},
            'by_mode': {m['mode']: m['count'] for m in mode_stats},
        }
