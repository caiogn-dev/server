"""
Unified Message Dispatcher — multi-channel messaging layer.

Wraps WhatsApp, Email, and Instagram providers behind a single interface.
Usage:
    from apps.messaging.dispatcher import dispatcher

    dispatcher.send(
        channel='whatsapp',
        recipient='+5511999999999',
        content={'type': 'text', 'text': 'Olá!'},
        store=store_instance,         # optional
        source='campaign',            # optional label
        source_id='campaign-uuid',    # optional external ref
    )
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .providers.base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

SUPPORTED_CHANNELS = ('whatsapp', 'email', 'instagram')


@dataclass
class DispatchMessage:
    """Normalised message passed to providers."""
    channel: str
    recipient: str
    content: Dict[str, Any]
    source: str = ''
    source_id: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)


def _get_provider(channel: str) -> BaseProvider:
    """Lazy-load the provider for a given channel."""
    if channel == 'whatsapp':
        from .providers.whatsapp_provider import WhatsAppProvider
        return WhatsAppProvider()
    if channel == 'email':
        from .providers.email_provider import EmailProvider
        return EmailProvider()
    if channel == 'instagram':
        from .providers.instagram_provider import InstagramProvider
        return InstagramProvider()
    raise ValueError(f"Unsupported channel: '{channel}'. Supported: {SUPPORTED_CHANNELS}")


class MessageDispatcher:
    """
    Single entry-point for sending messages across all channels.

    Features:
    - Auto-selects the correct provider based on channel
    - Validates recipient format per-channel before sending
    - Logs success/failure
    - Never raises — always returns a ProviderResult so callers can inspect
    """

    def send(
        self,
        channel: str,
        recipient: str,
        content: Dict[str, Any],
        store=None,
        source: str = '',
        source_id: str = '',
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProviderResult:
        """
        Send a message on the given channel.

        Args:
            channel:    'whatsapp' | 'email' | 'instagram'
            recipient:  Phone number, email address, or PSID depending on channel
            content:    Dict describing the message.  For text: {'type': 'text', 'text': '...'}
            store:      Store instance for context (optional; needed by WhatsApp provider)
            source:     Label for who triggered this (e.g. 'campaign', 'automation')
            source_id:  External reference ID
            metadata:   Arbitrary extra data attached to the message

        Returns:
            ProviderResult(success=True/False, external_id=..., error_code=..., error_message=...)
        """
        if channel not in SUPPORTED_CHANNELS:
            return ProviderResult(
                success=False,
                error_code='UNSUPPORTED_CHANNEL',
                error_message=f"Channel '{channel}' is not supported. Use one of: {SUPPORTED_CHANNELS}",
            )

        try:
            provider = _get_provider(channel)
        except Exception as exc:
            logger.error(f"[Dispatcher] Failed to load provider for '{channel}': {exc}")
            return ProviderResult(success=False, error_code='PROVIDER_LOAD_ERROR', error_message=str(exc))

        # Format and validate recipient
        formatted_recipient = provider.format_recipient(recipient)
        if not provider.validate_recipient(formatted_recipient):
            logger.warning(f"[Dispatcher] Invalid recipient '{recipient}' for channel '{channel}'")
            return ProviderResult(
                success=False,
                error_code='INVALID_RECIPIENT',
                error_message=f"Recipient '{recipient}' is not valid for channel '{channel}'",
            )

        message = DispatchMessage(
            channel=channel,
            recipient=formatted_recipient,
            content=content,
            source=source,
            source_id=source_id,
            metadata=metadata or {},
        )

        try:
            result = provider.send(message, store=store)
        except Exception as exc:
            logger.exception(f"[Dispatcher] Unhandled error sending via '{channel}': {exc}")
            return ProviderResult(success=False, error_code='DISPATCH_ERROR', error_message=str(exc))

        if result.success:
            logger.info(
                f"[Dispatcher] Sent via '{channel}' to '{formatted_recipient}' "
                f"(ext_id={result.external_id}, source={source})"
            )
        else:
            logger.warning(
                f"[Dispatcher] Failed via '{channel}' to '{formatted_recipient}': "
                f"{result.error_code} — {result.error_message}"
            )

        return result

    def send_bulk(
        self,
        channel: str,
        recipients: list,
        content: Dict[str, Any],
        store=None,
        source: str = '',
        source_id: str = '',
    ) -> Dict[str, ProviderResult]:
        """
        Send the same message to multiple recipients.

        Returns a dict mapping recipient → ProviderResult.
        """
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(
                channel=channel,
                recipient=recipient,
                content=content,
                store=store,
                source=source,
                source_id=source_id,
            )
        return results

    def channels(self) -> tuple:
        """Return the list of supported channel names."""
        return SUPPORTED_CHANNELS


# Singleton instance — import this in your code
dispatcher = MessageDispatcher()
