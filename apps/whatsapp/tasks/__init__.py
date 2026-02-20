"""
WhatsApp Celery tasks.
"""
import logging
import time
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

# Redis client for distributed locking
def get_redis_client():
    """Get Redis client for locking."""
    try:
        return redis.from_url(settings.CELERY_BROKER_URL)
    except Exception:
        return None

def acquire_lock(lock_name, timeout=60):
    """Acquire a distributed lock using Redis."""
    client = get_redis_client()
    if not client:
        return True  # No Redis, no lock
    
    # Try to acquire lock with NX (only if not exists)
    acquired = client.set(lock_name, "1", nx=True, ex=timeout)
    return acquired

def release_lock(lock_name):
    """Release a distributed lock."""
    client = get_redis_client()
    if client:
        client.delete(lock_name)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_webhook_event(self, event_id: str):
    """Process a webhook event asynchronously."""
    from ..models import WebhookEvent
    from ..services import WebhookService
    from ..repositories import WebhookEventRepository
    
    webhook_repo = WebhookEventRepository()
    
    try:
        event = webhook_repo.get_by_id(event_id)
        if not event:
            logger.error(f"Webhook event not found: {event_id}")
            return
        
        if event.processing_status in [
            WebhookEvent.ProcessingStatus.COMPLETED,
            WebhookEvent.ProcessingStatus.DUPLICATE
        ]:
            logger.info(f"Event already processed: {event_id}")
            return
        
        if event.processing_status == WebhookEvent.ProcessingStatus.PROCESSING:
            logger.info(f"Event is already processing: {event_id}")
            return
        
        service = WebhookService()
        service.process_event(event, post_process_inbound=True)
        
        logger.info(f"Webhook event processed: {event_id}")
        
    except Exception as e:
        logger.error(f"Error processing webhook event {event_id}: {str(e)}")
        try:
            webhook_repo.mark_as_failed(event, str(e))
        except Exception:
            logger.error("Failed to mark webhook event as failed", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_message_with_agent(self, message_id: str):
    """Process a message with AI Agent (Langchain)."""
    from ..models import Message
    from ..repositories import MessageRepository
    from apps.agents.services import AgentService
    from apps.conversations.services import ConversationService
    
    message_repo = MessageRepository()
    
    # Acquire distributed lock to prevent duplicate processing
    lock_name = f"process_message_with_agent:{message_id}"
    if not acquire_lock(lock_name, timeout=120):
        logger.info(f"Message {message_id} is already being processed by another worker")
        return
    
    try:
        message = message_repo.get_by_id(message_id)
        if not message:
            logger.error(f"Message not found: {message_id}")
            return
        
        if message.processed_by_agent:
            logger.info(f"Message already processed by AI Agent: {message_id}")
            return
        
        account = message.account
        
        if not account.default_agent:
            logger.info(f"No AI Agent configured for account: {account.id}")
            return
        
        conversation_service = ConversationService()
        
        if message.conversation and message.conversation.mode == 'human':
            logger.info(f"Conversation in human mode, skipping AI Agent: {message_id}")
            return
        
        agent = account.default_agent
        response_text = None
        
        try:
            # Use AgentService static method directly with timeout protection
            logger.info(f"Calling AgentService for message: {message_id}")
            result = AgentService.get_agent_response(
                agent_id=str(agent.id),
                message=message.text_body or '',
                session_id=str(message.conversation.id) if message.conversation else None,
                phone_number=message.from_number,
                conversation_id=str(message.conversation.id) if message.conversation else None
            )
            
            response_text = result.get('response', '')
            logger.info(f"Agent returned response of length {len(response_text) if response_text else 0} for message: {message_id}")
            
        except Exception as agent_error:
            logger.error(f"AgentService error for message {message_id}: {str(agent_error)}", exc_info=True)
            # Send fallback message on agent error
            response_text = "Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?"
        
        # Always mark as processed, even if there was an error
        try:
            message_repo.mark_as_processed_by_agent(message)
        except Exception as mark_error:
            logger.warning(f"Failed to mark message as processed: {str(mark_error)}")
        
        # Try to create order if conversation indicates a purchase intent
        if response_text and message.conversation:
            try:
                confirmation_words = [
                    'pedido confirmado', 'pedido registrado', 'pedido realizado',
                    'pedido foi confirmado', 'pedido foi registrado',
                    'resumo do pedido', 'total do pedido'
                ]
                response_lower = response_text.lower()
                if any(word in response_lower for word in confirmation_words):
                    logger.info(f"Attempting to create order from conversation: {message.conversation.id}")
                    order_result = try_create_order_from_conversation(
                        message.conversation,
                        message.from_number
                    )
                    if order_result and order_result.get('success'):
                        logger.info(f"Order created successfully: {order_result.get('order_number')}")
                        response_text += f"\n\n📋 *Pedido #{order_result.get('order_number')}* criado no sistema!"
                    else:
                        logger.warning(f"Could not create order: {order_result}")
            except Exception as order_error:
                logger.warning(f"Order creation error: {str(order_error)}")
        
        # Send response if we have one
        if response_text:
            try:
                send_agent_response.delay(
                    str(account.id),
                    message.from_number,
                    response_text,
                    str(message.whatsapp_message_id)
                )
                logger.info(f"Response queued for sending: {message_id}")
            except Exception as send_error:
                logger.error(f"Failed to queue response for message {message_id}: {str(send_error)}")
                # Try one more time with basic fallback
                try:
                    send_agent_response.delay(
                        str(account.id),
                        message.from_number,
                        "Obrigado pela mensagem! Em breve retornaremos.",
                        None
                    )
                except:
                    pass
        else:
            logger.warning(f"No response text generated for message: {message_id}")
        
        logger.info(f"Message processing completed: {message_id}")
        
    except Exception as e:
        logger.error(f"Error processing message with AI Agent {message_id}: {str(e)}")
        raise self.retry(exc=e)
    finally:
        # Always release the lock
        release_lock(lock_name)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_agent_response(self, account_id: str, to: str, response_text: str, reply_to: str = None):
    """Send AI Agent response as WhatsApp message."""
    from ..services import MessageService
    
    try:
        message_service = MessageService()
        # Ensure phone number has + prefix for E.164 format
        formatted_to = to if to.startswith('+') else '+' + to
        
        message_service.send_text_message(
            account_id=account_id,
            to=formatted_to,
            text=response_text,
            reply_to=reply_to,
            metadata={'source': 'ai_agent'}
        )
        logger.info(f"AI Agent response sent to {to}")
        
    except Exception as e:
        logger.error(f"Error sending AI Agent response: {str(e)}")
        raise self.retry(exc=e)


def _process_status_event(event, message_service):
    """Legacy status handler (kept for backward compatibility)."""
    payload = event.payload
    
    message_id = payload.get('id')
    status = payload.get('status')
    timestamp_str = payload.get('timestamp')
    
    timestamp = None
    if timestamp_str:
        try:
            timestamp = timezone.datetime.fromtimestamp(
                int(timestamp_str),
                tz=timezone.utc
            )
        except (ValueError, TypeError):
            pass
    
    message = message_service.update_message_status(
        whatsapp_message_id=message_id,
        status=status,
        timestamp=timestamp
    )
    
    if message:
        event.related_message = message
        event.save(update_fields=['related_message'])
    
    errors = payload.get('errors', [])
    if errors and message:
        error = errors[0]
        message_service.update_message_error(
            whatsapp_message_id=message_id,
            error_code=str(error.get('code', '')),
            error_message=error.get('title', '')
        )


def _process_error_event(event, message_service):
    """Legacy error handler (kept for backward compatibility)."""
    payload = event.payload
    
    error_code = payload.get('code')
    error_title = payload.get('title')
    error_message = payload.get('message', '')
    error_details = payload.get('error_data', {})
    
    logger.error(
        f"WhatsApp API Error: {error_code} - {error_title}",
        extra={
            'error_code': error_code,
            'error_title': error_title,
            'error_message': error_message,
            'error_details': error_details,
            'account_id': str(event.account.id) if event.account else None,
        }
    )


def try_create_order_from_conversation(conversation, phone_number: str) -> dict:
    """
    Try to create an order from conversation history.
    Returns order info if successful, empty dict otherwise.
    """
    from apps.agents.services import AgentService
    from apps.stores.models import StoreProduct
    
    try:
        # Get last messages from conversation
        messages = conversation.messages.filter(
            direction='inbound'
        ).order_by('-created_at')[:10]
        
        if not messages:
            return {}
        
        # Build conversation text
        conversation_text = "\n".join([m.text_body or "" for m in reversed(messages)])
        
        # Get store products
        store_products = StoreProduct.objects.filter(
            store__slug='pastita',
            is_active=True
        ).values('id', 'name', 'price')
        
        # Simple extraction - look for product names in conversation
        items = []
        for product in store_products:
            product_name_lower = product['name'].lower()
            # Check if product name appears in conversation
            if product_name_lower in conversation_text.lower():
                # Try to find quantity near the product name
                import re
                # Pattern: product name followed by numbers (quantity)
                pattern = rf"{re.escape(product_name_lower)}.*?(-?\s*\d+)"
                matches = re.findall(pattern, conversation_text.lower())
                quantity = 1
                if matches:
                    try:
                        quantity = int(matches[-1])
                        if quantity < 1:
                            quantity = 1
                        if quantity > 20:  # Sanity check
                            quantity = 1
                    except:
                        quantity = 1
                
                items.append({
                    'product_id': str(product['id']),
                    'quantity': quantity
                })
        
        if not items:
            return {}
        
        # Try to extract customer name from conversation
        customer_name = ""
        name_patterns = [
            r"(?:meu\s+nome\s+(?:é|e)|nome[\s:]*)([A-Za-z\s]+?)(?:\n|$|\.|-)",
            r"(?:sou\s+o|sou\s+a)\s+([A-Za-z\s]+?)(?:\n|$|\.|-)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, conversation_text, re.IGNORECASE)
            if match:
                customer_name = match.group(1).strip()
                break
        
        # Try to extract address
        delivery_address = ""
        address_patterns = [
            r"(?:endereço[\s:]*|entregar[\s:]*|rua[\s:]*)(.+?)(?:\n|$|telefone|forma\s+de\s+pagamento)",
            r"(?:casa|apartamento|condomínio)[\s:]*(.+?)(?:\n|$|telefone)",
        ]
        for pattern in address_patterns:
            match = re.search(pattern, conversation_text, re.IGNORECASE)
            if match:
                delivery_address = match.group(1).strip()
                break
        
        # Create order
        result = AgentService.create_order_from_conversation(
            phone_number=phone_number,
            items=items,
            customer_name=customer_name,
            delivery_address=delivery_address,
            notes=f"Pedido via WhatsApp - Cliente: {customer_name or 'Não informado'}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error trying to create order: {e}")
        return {}


@shared_task
def cleanup_old_webhook_events():
    """Cleanup old webhook events."""
    from ..services import WebhookService
    
    service = WebhookService()
    deleted = service.cleanup_old_events(days=30)
    logger.info(f"Cleaned up {deleted} old webhook events")


@shared_task
def sync_message_statuses():
    """Sync message statuses for pending messages."""
    from ..models import Message
    from ..repositories import MessageRepository
    
    message_repo = MessageRepository()
    
    pending_messages = message_repo.get_pending_messages(limit=100)
    
    for message in pending_messages:
        if (timezone.now() - message.created_at).total_seconds() > 300:
            message.status = Message.MessageStatus.FAILED
            message.error_message = "Message delivery timeout"
            message.failed_at = timezone.now()
            message.save()
            logger.warning(f"Message marked as failed due to timeout: {message.id}")
