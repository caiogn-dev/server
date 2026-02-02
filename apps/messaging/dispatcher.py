"""
Message Dispatcher - Central hub for all messaging channels.

This module provides a unified interface for sending messages across
WhatsApp, Instagram, Email, and other channels.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction

from .models import Message, MessageRule, MessageLog
from .providers.base import BaseProvider
from .providers.whatsapp_provider import WhatsAppProvider
from .providers.email_provider import EmailProvider
from .exceptions import MessageError, ChannelError, RateLimitError, QuietHoursError

logger = logging.getLogger(__name__)


class MessageDispatcher:
    """
    Central dispatcher for all messaging channels.
    
    Usage:
        dispatcher = MessageDispatcher()
        
        # Send immediately
        result = dispatcher.send_message(
            channel='whatsapp',
            recipient='+5511999999999',
            content={'text': 'Hello!'},
            store_id='store-uuid'
        )
        
        # Schedule for later
        result = dispatcher.schedule_message(
            channel='email',
            recipient='customer@example.com',
            content={'subject': 'Hello', 'body': '...'},
            scheduled_at=timezone.now() + timedelta(hours=1)
        )
    """
    
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize all available providers."""
        self._providers = {
            Message.Channel.WHATSAPP: WhatsAppProvider(),
            Message.Channel.EMAIL: EmailProvider(),
            # Add more providers as needed:
            # Message.Channel.INSTAGRAM: InstagramProvider(),
            # Message.Channel.SMS: SMSProvider(),
        }
    
    def get_provider(self, channel: str) -> BaseProvider:
        """Get provider for a channel."""
        if channel not in self._providers:
            raise ChannelError(f"Unknown channel: {channel}")
        return self._providers[channel]
    
    def send_message(
        self,
        channel: str,
        recipient: str,
        content: Dict[str, Any],
        store_id: Optional[str] = None,
        template_id: Optional[str] = None,
        priority: int = Message.Priority.NORMAL,
        source: str = 'api',
        source_id: str = '',
        metadata: Optional[Dict] = None,
        user_id: Optional[int] = None,
        bypass_rules: bool = False
    ) -> Message:
        """
        Send a message immediately.
        
        Args:
            channel: Channel to use (whatsapp, email, etc.)
            recipient: Recipient address (phone, email, etc.)
            content: Message content
            store_id: Optional store context
            template_id: Optional template to use
            priority: Message priority
            source: Source of the message (api, automation, campaign)
            source_id: ID of the source object
            metadata: Additional metadata
            user_id: ID of the user sending the message
            bypass_rules: Skip rule checking (use with caution)
        
        Returns:
            Message object with status
        """
        # Validate channel
        provider = self.get_provider(channel)
        
        # Create message record
        message = Message.objects.create(
            store_id=store_id,
            channel=channel,
            recipient=recipient,
            content=content,
            text=content.get('text', content.get('body', '')),
            template_id=template_id,
            priority=priority,
            source=source,
            source_id=source_id,
            metadata=metadata or {},
            created_by_id=user_id,
            status=Message.Status.PENDING
        )
        
        # Check rules
        if not bypass_rules:
            try:
                self._check_rules(message)
            except (RateLimitError, QuietHoursError) as e:
                message.mark_failed(error_code='RULE_VIOLATION', error_message=str(e))
                raise
        
        # Send via provider
        return self._send_via_provider(message, provider)
    
    def schedule_message(
        self,
        channel: str,
        recipient: str,
        content: Dict[str, Any],
        scheduled_at: datetime,
        store_id: Optional[str] = None,
        template_id: Optional[str] = None,
        priority: int = Message.Priority.NORMAL,
        source: str = 'api',
        source_id: str = '',
        metadata: Optional[Dict] = None,
        user_id: Optional[int] = None
    ) -> Message:
        """
        Schedule a message for future delivery.
        """
        # Validate scheduled time
        if scheduled_at <= timezone.now():
            raise MessageError("Scheduled time must be in the future")
        
        message = Message.objects.create(
            store_id=store_id,
            channel=channel,
            recipient=recipient,
            content=content,
            text=content.get('text', content.get('body', '')),
            template_id=template_id,
            priority=priority,
            source=source,
            source_id=source_id,
            metadata=metadata or {},
            created_by_id=user_id,
            status=Message.Status.PENDING,
            scheduled_at=scheduled_at
        )
        
        logger.info(f"Message scheduled for {scheduled_at}: {message.id}")
        return message
    
    def send_template(
        self,
        template_id: str,
        recipient: str,
        variables: Dict[str, Any],
        store_id: Optional[str] = None,
        **kwargs
    ) -> Message:
        """
        Send using a template.
        """
        from .models import MessageTemplate
        
        try:
            template = MessageTemplate.objects.get(id=template_id, is_active=True)
        except MessageTemplate.DoesNotExist:
            raise MessageError(f"Template not found: {template_id}")
        
        # Render template
        rendered = template.render(variables)
        
        # Determine channel from template
        channel = template.channel
        if channel == MessageTemplate.Channel.UNIVERSAL:
            channel = kwargs.get('channel', 'whatsapp')
        
        content = {
            'text': rendered['body'],
            'html': rendered.get('html_body'),
            'subject': rendered.get('subject'),
            'buttons': template.buttons,
            'media_url': template.media_url,
        }
        
        message = self.send_message(
            channel=channel,
            recipient=recipient,
            content=content,
            store_id=store_id,
            template_id=template_id,
            **kwargs
        )
        
        # Record template usage
        template.record_usage()
        
        return message
    
    def process_scheduled(self, batch_size: int = 100) -> int:
        """
        Process scheduled messages that are due.
        Called by Celery task.
        
        Returns:
            Number of messages processed
        """
        now = timezone.now()
        
        messages = Message.objects.filter(
            status=Message.Status.PENDING,
            scheduled_at__lte=now
        ).order_by('priority', 'scheduled_at')[:batch_size]
        
        processed = 0
        for message in messages:
            try:
                provider = self.get_provider(message.channel)
                self._send_via_provider(message, provider)
                processed += 1
            except Exception as e:
                logger.error(f"Failed to send scheduled message {message.id}: {e}")
                message.mark_failed(error_message=str(e))
        
        return processed
    
    def retry_failed(self, max_retries: int = 3, batch_size: int = 50) -> int:
        """
        Retry failed messages.
        
        Returns:
            Number of messages retried
        """
        messages = Message.objects.filter(
            status=Message.Status.FAILED,
            retry_count__lt=max_retries
        )[:batch_size]
        
        retried = 0
        for message in messages:
            if not message.can_retry():
                continue
            
            try:
                provider = self.get_provider(message.channel)
                message.retry_count += 1
                message.status = Message.Status.PENDING
                message.save(update_fields=['retry_count', 'status'])
                
                self._send_via_provider(message, provider)
                retried += 1
            except Exception as e:
                logger.error(f"Retry failed for message {message.id}: {e}")
                message.mark_failed(error_message=str(e))
        
        return retried
    
    def _check_rules(self, message: Message):
        """
        Check messaging rules before sending.
        Raises RuleViolationError if rules are violated.
        """
        # Get applicable rules
        rules = MessageRule.objects.filter(
            models.Q(store=message.store) | models.Q(store__isnull=True),
            is_active=True
        ).order_by('priority')
        
        for rule in rules:
            if not rule.applies_to(message.channel):
                continue
            
            if rule.rule_type == MessageRule.RuleType.QUIET_HOURS:
                self._check_quiet_hours(rule, message)
            elif rule.rule_type == MessageRule.RuleType.RATE_LIMIT:
                self._check_rate_limit(rule, message)
            elif rule.rule_type == MessageRule.RuleType.MAX_DAILY:
                self._check_max_daily(rule, message)
    
    def _check_quiet_hours(self, rule: MessageRule, message: Message):
        """Check if current time is within quiet hours."""
        config = rule.config
        start_time = config.get('start', '22:00')
        end_time = config.get('end', '08:00')
        timezone_str = config.get('timezone', 'America/Sao_Paulo')
        
        import pytz
        tz = pytz.timezone(timezone_str)
        now = timezone.now().astimezone(tz)
        current_time = now.strftime('%H:%M')
        
        # Check if current time is within quiet hours
        is_quiet = False
        if start_time <= end_time:
            is_quiet = start_time <= current_time <= end_time
        else:
            # Quiet hours span midnight (e.g., 22:00 - 08:00)
            is_quiet = current_time >= start_time or current_time <= end_time
        
        if is_quiet:
            raise QuietHoursError(
                f"Cannot send messages during quiet hours ({start_time} - {end_time})"
            )
    
    def _check_rate_limit(self, rule: MessageRule, message: Message):
        """Check rate limit for recipient."""
        config = rule.config
        max_messages = config.get('max_messages', 10)
        window_minutes = config.get('window_minutes', 60)
        
        window_start = timezone.now() - timedelta(minutes=window_minutes)
        
        recent_count = Message.objects.filter(
            recipient=message.recipient,
            channel=message.channel,
            created_at__gte=window_start,
            status__in=[Message.Status.SENT, Message.Status.DELIVERED, Message.Status.PENDING]
        ).count()
        
        if recent_count >= max_messages:
            raise RateLimitError(
                f"Rate limit exceeded: {max_messages} messages per {window_minutes} minutes"
            )
    
    def _check_max_daily(self, rule: MessageRule, message: Message):
        """Check daily message limit for recipient."""
        config = rule.config
        max_daily = config.get('max_daily', 50)
        
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        daily_count = Message.objects.filter(
            recipient=message.recipient,
            channel=message.channel,
            created_at__gte=today_start,
            status__in=[Message.Status.SENT, Message.Status.DELIVERED, Message.Status.PENDING]
        ).count()
        
        if daily_count >= max_daily:
            raise RateLimitError(f"Daily limit exceeded: {max_daily} messages per day")
    
    def _send_via_provider(self, message: Message, provider: BaseProvider) -> Message:
        """Send message via provider."""
        import time
        
        start_time = time.time()
        message.status = Message.Status.SENDING
        message.save(update_fields=['status'])
        
        try:
            # Get store context for provider
            store = message.store
            
            # Send via provider
            result = provider.send(
                message=message,
                store=store
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Update message with result
            if result.success:
                message.mark_sent(external_id=result.external_id)
                
                # Log success
                MessageLog.objects.create(
                    message=message,
                    level=MessageLog.LogLevel.INFO,
                    action='sent',
                    description='Message sent successfully',
                    response_data=result.raw_response,
                    duration_ms=duration_ms
                )
            else:
                message.mark_failed(
                    error_code=result.error_code,
                    error_message=result.error_message
                )
                
                # Log failure
                MessageLog.objects.create(
                    message=message,
                    level=MessageLog.LogLevel.ERROR,
                    action='send_failed',
                    description=result.error_message,
                    response_data=result.raw_response,
                    duration_ms=duration_ms
                )
            
            return message
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            message.mark_failed(error_message=str(e))
            
            # Log error
            MessageLog.objects.create(
                message=message,
                level=MessageLog.LogLevel.ERROR,
                action='send_error',
                description=str(e),
                duration_ms=duration_ms
            )
            
            logger.exception(f"Error sending message {message.id}")
            raise MessageError(f"Failed to send message: {e}") from e
    
    def get_message_status(self, message_id: str) -> Optional[Message]:
        """Get current status of a message."""
        try:
            return Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return None
    
    def cancel_message(self, message_id: str) -> bool:
        """
        Cancel a pending or scheduled message.
        
        Returns:
            True if cancelled, False otherwise
        """
        try:
            message = Message.objects.get(
                id=message_id,
                status__in=[Message.Status.PENDING, Message.Status.QUEUED]
            )
            message.status = Message.Status.CANCELLED
            message.save(update_fields=['status'])
            return True
        except Message.DoesNotExist:
            return False
