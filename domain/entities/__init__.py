"""
Domain entities - Core business objects.
"""
from .social_message import (
    # Enums
    MessageDirection,
    MessageStatus,
    MessageType,
    Platform,
    # Data classes
    SocialContact,
    MediaContent,
    SocialMessage,
    SocialConversation,
    # Abstract base class
    BaseSocialMessageService,
    # Factory
    SocialMessageServiceFactory,
)

__all__ = [
    'MessageDirection',
    'MessageStatus',
    'MessageType',
    'Platform',
    'SocialContact',
    'MediaContent',
    'SocialMessage',
    'SocialConversation',
    'BaseSocialMessageService',
    'SocialMessageServiceFactory',
]
