"""
Read-only aggregation service for the multichannel conversations hub.
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.contrib.auth.models import AnonymousUser

from apps.instagram.models import InstagramConversation
from apps.messaging.models import MessengerConversation

from ..models import Conversation


class UniversalConversationService:
    """Build a normalized, read-only conversation list across platforms."""

    def list_conversations(self, user) -> List[Dict[str, Any]]:
        conversations: List[Dict[str, Any]] = []
        conversations.extend(self._build_whatsapp_rows(user))
        conversations.extend(self._build_instagram_rows(user))
        conversations.extend(self._build_messenger_rows(user))
        conversations.sort(
            key=lambda item: item.get("sort_at") or item.get("last_message_at") or "",
            reverse=True,
        )
        return conversations

    def _build_whatsapp_rows(self, user) -> List[Dict[str, Any]]:
        from apps.conversations.api.views import _accessible_conversations

        queryset = _accessible_conversations(user)
        rows: List[Dict[str, Any]] = []

        for conv in queryset:
            last_message = conv.messages.order_by("-created_at").first()
            rows.append(
                {
                    "id": f"whatsapp:{conv.id}",
                    "platform": "whatsapp",
                    "platform_icon_key": "whatsapp",
                    "source_conversation_id": str(conv.id),
                    "account_id": str(conv.account_id),
                    "display_name": conv.contact_name or conv.phone_number,
                    "secondary_identifier": conv.phone_number,
                    "last_message_preview": self._whatsapp_preview(last_message),
                    "last_message_at": conv.last_message_at or conv.created_at,
                    "unread_count": conv.messages.filter(
                        direction="inbound",
                        read_at__isnull=True,
                    ).count(),
                    "status": conv.status,
                    "route": "/whatsapp/inbox",
                    "route_params": {"conversation": str(conv.id)},
                    "is_actionable": True,
                    "sort_at": conv.last_message_at or conv.created_at,
                }
            )

        return rows

    def _build_instagram_rows(self, user) -> List[Dict[str, Any]]:
        queryset = InstagramConversation.objects.filter(is_active=True)
        if not self._is_staff(user):
            queryset = queryset.filter(account__user=user)

        rows: List[Dict[str, Any]] = []
        for conv in queryset.order_by("-last_message_at", "-created_at"):
            last_message = conv.messages.filter(is_unsent=False).order_by("-created_at").first()
            rows.append(
                {
                    "id": f"instagram:{conv.id}",
                    "platform": "instagram",
                    "platform_icon_key": "instagram",
                    "source_conversation_id": str(conv.id),
                    "account_id": str(conv.account_id),
                    "display_name": conv.participant_name or conv.participant_username or conv.participant_id,
                    "secondary_identifier": (
                        f"@{conv.participant_username}"
                        if conv.participant_username
                        else conv.participant_id
                    ),
                    "last_message_preview": self._instagram_preview(last_message),
                    "last_message_at": conv.last_message_at or conv.created_at,
                    "unread_count": conv.unread_count,
                    "status": "active" if conv.is_active else "closed",
                    "route": "/instagram/inbox",
                    "route_params": {
                        "account": str(conv.account_id),
                        "conversation": str(conv.id),
                    },
                    "is_actionable": True,
                    "sort_at": conv.last_message_at or conv.created_at,
                }
            )

        return rows

    def _build_messenger_rows(self, user) -> List[Dict[str, Any]]:
        queryset = MessengerConversation.objects.filter(is_active=True)
        if not self._is_staff(user):
            queryset = queryset.filter(account__user=user)

        rows: List[Dict[str, Any]] = []
        for conv in queryset.order_by("-last_message_at", "-created_at"):
            last_message = conv.messages.order_by("-created_at").first()
            rows.append(
                {
                    "id": f"messenger:{conv.id}",
                    "platform": "messenger",
                    "platform_icon_key": "messenger",
                    "source_conversation_id": str(conv.id),
                    "account_id": str(conv.account_id),
                    "display_name": conv.participant_name or conv.psid,
                    "secondary_identifier": conv.psid,
                    "last_message_preview": self._messenger_preview(last_message),
                    "last_message_at": conv.last_message_at or conv.created_at,
                    "unread_count": conv.unread_count,
                    "status": "active" if conv.is_active else "closed",
                    "route": "/messenger/inbox",
                    "route_params": {
                        "account": str(conv.account_id),
                        "conversation": str(conv.id),
                    },
                    "is_actionable": True,
                    "sort_at": conv.last_message_at or conv.created_at,
                }
            )

        return rows

    def _whatsapp_preview(self, message) -> str:
        if not message:
            return ""
        if getattr(message, "text_body", ""):
            return message.text_body[:120]
        if getattr(message, "media_filename", ""):
            return f"Arquivo: {message.media_filename}"
        message_type = getattr(message, "message_type", "")
        return message_type.replace("_", " ").title()

    def _instagram_preview(self, message) -> str:
        if not message:
            return ""
        if getattr(message, "content", ""):
            return message.content[:120]
        message_type = getattr(message, "message_type", "")
        return message_type.replace("_", " ").title()

    def _messenger_preview(self, message) -> str:
        if not message:
            return ""
        if getattr(message, "content", ""):
            return message.content[:120]
        attachment_type = getattr(message, "attachment_type", "")
        if attachment_type:
            return attachment_type.replace("_", " ").title()
        message_type = getattr(message, "message_type", "")
        return message_type.replace("_", " ").title()

    def _is_staff(self, user) -> bool:
        if isinstance(user, AnonymousUser):
            return False
        return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
