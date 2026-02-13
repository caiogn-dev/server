"""
Social Message Abstraction - Base classes for WhatsApp and Instagram messaging.

This module provides a unified interface for handling messages across different
social platforms (WhatsApp, Instagram) without duplicating code.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, TypeVar, Generic


class MessageDirection(str, Enum):
    """Message direction."""
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class MessageStatus(str, Enum):
    """Message delivery status."""
    PENDING = 'pending'
    SENT = 'sent'
    DELIVERED = 'delivered'
    READ = 'read'
    FAILED = 'failed'


class MessageType(str, Enum):
    """Message content type."""
    TEXT = 'text'
    IMAGE = 'image'
    VIDEO = 'video'
    AUDIO = 'audio'
    DOCUMENT = 'document'
    STICKER = 'sticker'
    LOCATION = 'location'
    CONTACTS = 'contacts'
    INTERACTIVE = 'interactive'
    TEMPLATE = 'template'
    REACTION = 'reaction'
    BUTTON = 'button'
    ORDER = 'order'
    STORY_MENTION = 'story_mention'
    SHARE = 'share'
    SYSTEM = 'system'
    UNKNOWN = 'unknown'


class Platform(str, Enum):
    """Social media platform."""
    WHATSAPP = 'whatsapp'
    INSTAGRAM = 'instagram'


@dataclass
class SocialContact:
    """Represents a contact on a social platform."""
    platform_id: str  # WhatsApp wa_id or Instagram user_id
    phone_number: Optional[str] = None  # Only for WhatsApp
    username: Optional[str] = None  # Only for Instagram
    name: Optional[str] = None
    profile_picture_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaContent:
    """Media content attached to a message."""
    media_type: str  # image, video, audio, document, sticker
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    filename: Optional[str] = None
    caption: Optional[str] = None


@dataclass
class SocialMessage:
    """
    Platform-agnostic message representation.
    
    This is the core entity that represents a message regardless of
    whether it came from WhatsApp or Instagram.
    """
    id: str
    platform: Platform
    platform_message_id: str  # WhatsApp message ID or Instagram mid
    account_id: str  # WhatsApp account ID or Instagram account ID
    
    direction: MessageDirection
    message_type: MessageType
    status: MessageStatus
    
    sender: SocialContact
    recipient: SocialContact
    
    text_content: str = ''
    media: Optional[MediaContent] = None
    raw_content: Dict[str, Any] = field(default_factory=dict)
    
    reply_to_message_id: Optional[str] = None
    
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'platform': self.platform.value,
            'platform_message_id': self.platform_message_id,
            'account_id': self.account_id,
            'direction': self.direction.value,
            'message_type': self.message_type.value,
            'status': self.status.value,
            'sender': {
                'platform_id': self.sender.platform_id,
                'phone_number': self.sender.phone_number,
                'username': self.sender.username,
                'name': self.sender.name,
            },
            'recipient': {
                'platform_id': self.recipient.platform_id,
                'phone_number': self.recipient.phone_number,
                'username': self.recipient.username,
                'name': self.recipient.name,
            },
            'text_content': self.text_content,
            'media': {
                'media_type': self.media.media_type,
                'media_id': self.media.media_id,
                'media_url': self.media.media_url,
                'caption': self.media.caption,
            } if self.media else None,
            'reply_to_message_id': self.reply_to_message_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'error_code': self.error_code,
            'error_message': self.error_message,
        }


@dataclass
class SocialConversation:
    """
    Platform-agnostic conversation representation.
    """
    id: str
    platform: Platform
    account_id: str
    participant: SocialContact
    
    status: str = 'open'
    mode: str = 'auto'  # auto, human, hybrid
    
    last_message_at: Optional[datetime] = None
    last_message_preview: str = ''
    message_count: int = 0
    unread_count: int = 0
    
    assigned_agent_id: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Type variable for generic message service
TMessage = TypeVar('TMessage')
TConversation = TypeVar('TConversation')


class BaseSocialMessageService(ABC, Generic[TMessage, TConversation]):
    """
    Abstract base class for social messaging services.
    
    Implementations should be created for each platform (WhatsApp, Instagram)
    to handle platform-specific API calls while maintaining a consistent interface.
    """
    
    @property
    @abstractmethod
    def platform(self) -> Platform:
        """Return the platform this service handles."""
        pass
    
    # ==================== Send Messages ====================
    
    @abstractmethod
    def send_text(
        self,
        recipient_id: str,
        text: str,
        reply_to: Optional[str] = None
    ) -> SocialMessage:
        """
        Send a text message.
        
        Args:
            recipient_id: Platform-specific recipient ID
            text: Message text
            reply_to: Optional message ID to reply to
            
        Returns:
            SocialMessage representing the sent message
        """
        pass
    
    @abstractmethod
    def send_image(
        self,
        recipient_id: str,
        image_url: Optional[str] = None,
        image_id: Optional[str] = None,
        caption: Optional[str] = None
    ) -> SocialMessage:
        """Send an image message."""
        pass
    
    @abstractmethod
    def send_template(
        self,
        recipient_id: str,
        template_name: str,
        language: str,
        components: List[Dict[str, Any]]
    ) -> SocialMessage:
        """Send a template message (WhatsApp) or structured message (Instagram)."""
        pass
    
    # ==================== Process Incoming ====================
    
    @abstractmethod
    def process_incoming_message(
        self,
        webhook_data: Dict[str, Any]
    ) -> Optional[SocialMessage]:
        """
        Process an incoming message from webhook.
        
        Args:
            webhook_data: Raw webhook payload
            
        Returns:
            SocialMessage if successfully processed, None otherwise
        """
        pass
    
    @abstractmethod
    def process_status_update(
        self,
        webhook_data: Dict[str, Any]
    ) -> Optional[SocialMessage]:
        """
        Process a message status update from webhook.
        
        Args:
            webhook_data: Raw webhook payload
            
        Returns:
            Updated SocialMessage if found, None otherwise
        """
        pass
    
    # ==================== Conversation Management ====================
    
    @abstractmethod
    def get_or_create_conversation(
        self,
        participant_id: str,
        participant_name: Optional[str] = None
    ) -> SocialConversation:
        """Get or create a conversation with a participant."""
        pass
    
    @abstractmethod
    def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 50,
        before: Optional[datetime] = None
    ) -> List[SocialMessage]:
        """Get message history for a conversation."""
        pass
    
    # ==================== Broadcast ====================
    
    @abstractmethod
    def broadcast_new_message(self, message: SocialMessage) -> bool:
        """Broadcast a new message to connected clients via WebSocket."""
        pass
    
    @abstractmethod
    def broadcast_status_update(
        self,
        message_id: str,
        status: MessageStatus,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """Broadcast a status update to connected clients."""
        pass
    
    # ==================== Utilities ====================
    
    def normalize_phone_number(self, phone: str) -> str:
        """Normalize a phone number to standard format."""
        # Remove all non-digit characters
        digits = ''.join(c for c in phone if c.isdigit())
        # Ensure it starts with country code
        if not digits.startswith('55') and len(digits) <= 11:
            digits = '55' + digits
        return digits
    
    def generate_idempotency_key(self, *args) -> str:
        """Generate an idempotency key from arguments."""
        import hashlib
        key_string = ':'.join(str(arg) for arg in args)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]


class SocialMessageServiceFactory:
    """
    Factory for creating platform-specific message services.
    
    Usage:
        factory = SocialMessageServiceFactory()
        factory.register(Platform.WHATSAPP, WhatsAppMessageService)
        factory.register(Platform.INSTAGRAM, InstagramMessageService)
        
        service = factory.create(Platform.WHATSAPP, account)
        service.send_text(recipient, "Hello!")
    """
    
    _services: Dict[Platform, type] = {}
    
    @classmethod
    def register(cls, platform: Platform, service_class: type):
        """Register a service class for a platform."""
        cls._services[platform] = service_class
    
    @classmethod
    def create(cls, platform: Platform, account) -> BaseSocialMessageService:
        """
        Create a message service for the given platform and account.
        
        Args:
            platform: The social platform
            account: Platform-specific account object
            
        Returns:
            Configured message service instance
            
        Raises:
            ValueError: If no service is registered for the platform
        """
        if platform not in cls._services:
            raise ValueError(f"No service registered for platform: {platform}")
        
        return cls._services[platform](account)
    
    @classmethod
    def get_available_platforms(cls) -> List[Platform]:
        """Get list of platforms with registered services."""
        return list(cls._services.keys())
