"""
Webhook Service - Process incoming webhooks from Meta.
"""
import logging
import hashlib
import mimetypes
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from django.db import IntegrityError
from django.db.models import Q
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db import transaction
from celery import current_app
from apps.core.utils import (
    verify_webhook_signature,
    generate_idempotency_key,
    normalize_phone_number,
    build_absolute_media_url,
    mime_to_extension,
)
from apps.core.exceptions import WebhookValidationError
from ..models import WhatsAppAccount, WebhookEvent, Message
from ..repositories import WebhookEventRepository, WhatsAppAccountRepository
from .broadcast_service import get_broadcast_service
from .whatsapp_api_service import WhatsAppAPIService

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for processing Meta webhooks."""

    def __init__(self):
        self.webhook_repo = WebhookEventRepository()
        self.account_repo = WhatsAppAccountRepository()
        self.broadcast = get_broadcast_service()

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str:
        """Verify webhook subscription."""
        verify_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook verification successful")
            return challenge
        
        logger.warning(f"Webhook verification failed: mode={mode}")
        raise WebhookValidationError(message="Webhook verification failed")

    def validate_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook signature."""
        app_secret = settings.WHATSAPP_APP_SECRET
        
        if not app_secret:
            logger.warning("WHATSAPP_APP_SECRET not configured, skipping signature validation")
            return True
        
        if not signature:
            logger.warning("No signature provided in webhook request")
            return False
        
        is_valid = verify_webhook_signature(payload, signature, app_secret)
        
        if not is_valid:
            logger.warning("Invalid webhook signature")
        
        return is_valid

    def process_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> List[WebhookEvent]:
        """Process incoming webhook payload."""
        events = []
        
        entries = payload.get('entry', [])
        
        for entry in entries:
            changes = entry.get('changes', [])
            waba_id = entry.get('id')
            
            for change in changes:
                if change.get('field') != 'messages':
                    continue
                
                value = change.get('value', {})
                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
                display_phone = metadata.get('display_phone_number')
                
                account = self._resolve_account(
                    phone_number_id=phone_number_id,
                    display_phone=display_phone,
                    waba_id=waba_id
                )
                
                if not account:
                    logger.warning(
                        "Account not found for webhook event",
                        extra={
                            'phone_number_id': phone_number_id,
                            'display_phone': display_phone,
                            'waba_id': waba_id,
                        }
                    )
                    continue
                
                messages = value.get('messages', [])
                for message_data in messages:
                    event = self._process_message_event(
                        account=account,
                        message_data=message_data,
                        contacts=value.get('contacts', []),
                        headers=headers
                    )
                    if event:
                        events.append(event)
                
                statuses = value.get('statuses', [])
                for status_data in statuses:
                    event = self._process_status_event(
                        account=account,
                        status_data=status_data,
                        headers=headers
                    )
                    if event:
                        events.append(event)
                
                errors = value.get('errors', [])
                for error_data in errors:
                    event = self._process_error_event(
                        account=account,
                        error_data=error_data,
                        headers=headers
                    )
                    if event:
                        events.append(event)
        
        return events

    def _resolve_account(
        self,
        phone_number_id: Optional[str],
        display_phone: Optional[str],
        waba_id: Optional[str]
    ) -> Optional[WhatsAppAccount]:
        """Resolve WhatsApp account from webhook metadata with fallbacks."""
        account = None
        
        if phone_number_id:
            account = self.account_repo.get_by_phone_number_id(phone_number_id)
        
        if not account and display_phone:
            normalized = normalize_phone_number(display_phone)
            if normalized:
                account = WhatsAppAccount.objects.filter(
                    is_active=True
                ).filter(
                    Q(display_phone_number__icontains=normalized) |
                    Q(phone_number__icontains=normalized)
                ).first()
        
        if not account and waba_id:
            account = WhatsAppAccount.objects.filter(
                is_active=True,
                waba_id=waba_id
            ).first()
        
        # If we found an account but phone_number_id has changed, update it
        if account and phone_number_id and account.phone_number_id != phone_number_id:
            try:
                account.phone_number_id = phone_number_id
                if display_phone and not account.display_phone_number:
                    account.display_phone_number = display_phone
                account.save(update_fields=['phone_number_id', 'display_phone_number', 'updated_at'])
                logger.warning(
                    f"Updated account phone_number_id from webhook: account={account.id}"
                )
            except IntegrityError:
                logger.error(
                    "Failed to update phone_number_id (unique conflict)",
                    extra={'account_id': str(account.id), 'phone_number_id': phone_number_id}
                )
        
        return account

    def _process_message_event(
        self,
        account: WhatsAppAccount,
        message_data: Dict[str, Any],
        contacts: List[Dict],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process a message event."""
        message_id = message_data.get('id')
        event_id = generate_idempotency_key('message', message_id)
        
        if self.webhook_repo.exists_by_event_id(event_id):
            logger.info(f"Duplicate message event: {event_id}")
            return None

        contact_info = {}
        if contacts:
            contact = contacts[0]
            contact_info = {
                'wa_id': contact.get('wa_id'),
                'profile': contact.get('profile', {})
            }

        try:
            event = self.webhook_repo.create(
                account=account,
                event_id=event_id,
                event_type=WebhookEvent.EventType.MESSAGE,
                payload={
                    'message': message_data,
                    'contact': contact_info
                },
                headers=headers
            )
        except IntegrityError:
            logger.info(f"Duplicate message event (race condition): {event_id}")
            return None

        logger.info(f"Message event created: {event.id}")
        return event

    def _process_status_event(
        self,
        account: WhatsAppAccount,
        status_data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process a status update event."""
        message_id = status_data.get('id')
        status = status_data.get('status')
        timestamp = status_data.get('timestamp')
        
        event_id = generate_idempotency_key('status', message_id, status, timestamp)
        
        if self.webhook_repo.exists_by_event_id(event_id):
            logger.info(f"Duplicate status event: {event_id}")
            return None

        try:
            event = self.webhook_repo.create(
                account=account,
                event_id=event_id,
                event_type=WebhookEvent.EventType.STATUS,
                payload=status_data,
                headers=headers
            )
        except IntegrityError:
            logger.info(f"Duplicate status event (race condition): {event_id}")
            return None

        logger.info(f"Status event created: {event.id}")
        return event

    def _process_error_event(
        self,
        account: WhatsAppAccount,
        error_data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process an error event."""
        error_code = error_data.get('code')
        error_title = error_data.get('title')
        timestamp = str(timezone.now().timestamp())
        
        event_id = generate_idempotency_key('error', error_code, timestamp)
        
        event = self.webhook_repo.create(
            account=account,
            event_id=event_id,
            event_type=WebhookEvent.EventType.ERROR,
            payload=error_data,
            headers=headers
        )
        
        logger.warning(f"Error event created: {event.id} - {error_code}: {error_title}")
        return event

    def get_pending_events(self, limit: int = 100) -> List[WebhookEvent]:
        """Get pending events for processing."""
        return list(self.webhook_repo.get_pending_events(limit))

    def get_failed_events_for_retry(
        self,
        max_retries: int = 3,
        limit: int = 100
    ) -> List[WebhookEvent]:
        """Get failed events eligible for retry."""
        return list(self.webhook_repo.get_failed_events_for_retry(max_retries, limit))

    def mark_event_processing(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as processing."""
        return self.webhook_repo.mark_as_processing(event)

    def mark_event_completed(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as completed."""
        return self.webhook_repo.mark_as_completed(event)

    def mark_event_failed(
        self,
        event: WebhookEvent,
        error_message: str
    ) -> WebhookEvent:
        """Mark event as failed."""
        return self.webhook_repo.mark_as_failed(event, error_message)

    def cleanup_old_events(self, days: int = 30) -> int:
        """Cleanup old processed events."""
        deleted = self.webhook_repo.cleanup_old_events(days)
        logger.info(f"Cleaned up {deleted} old webhook events")
        return deleted

    @transaction.atomic
    def process_event(self, event: WebhookEvent, post_process_inbound: bool = False) -> Optional[Message]:
        """
        Process a webhook event and broadcast updates.
        
        This is called by the Celery task after the event is saved.
        It handles:
        - MESSAGE events: Create/update Message record, broadcast to clients
        - STATUS events: Update message status, broadcast to clients
        - ERROR events: Log error, broadcast to clients
        
        Args:
            event: WebhookEvent to process
            
        Returns:
            Message object if a message was created/updated, None otherwise
        """
        try:
            self.mark_event_processing(event)
            
            if event.event_type == WebhookEvent.EventType.MESSAGE:
                message = self._process_inbound_message(event)
                if post_process_inbound and message:
                    self.post_process_inbound_message(event, message)
                self.mark_event_completed(event)
                return message
            
            elif event.event_type == WebhookEvent.EventType.STATUS:
                message = self._process_status_update(event)
                self.mark_event_completed(event)
                return message
            
            elif event.event_type == WebhookEvent.EventType.ERROR:
                self._process_error(event)
                self.mark_event_completed(event)
                return None
            
            else:
                logger.warning(f"Unknown event type: {event.event_type}")
                self.mark_event_completed(event)
                return None
                
        except Exception as e:
            logger.error(f"Error processing event {event.id}: {e}", exc_info=True)
            self.mark_event_failed(event, str(e))
            raise

    def post_process_inbound_message(self, event: WebhookEvent, message: Message) -> None:
        """
        Processa mensagem inbound pelo pipeline canônico de automação.

        Pipeline:
        1. Garante que a conversa existe (get_or_create)
        2. Atualiza nome do contato se disponível
        3. Resolve contexto (store / profile / account)
        4. Executa UnifiedService (intents → handlers → templates → LLM)
        5a. Se UnifiedService retornou resposta interativa → envia imediatamente
        5b. Se retornou texto → enfileira via Celery para rate-limit seguro
        6. Se UnifiedService não produziu resposta (timeout / erro / None) → fallback
           para agente LLM direto, SOMENTE se LLM habilitado e agente configurado

        Métricas registradas via logger estruturado:
        - pipeline.source: onde a resposta foi gerada (handler/template/llm/fallback/agent)
        - pipeline.duration_ms: tempo total do step do orquestrador
        - pipeline.timeout: se o orquestrador excedeu o limite de tempo
        - pipeline.dropped: se a mensagem não recebeu resposta alguma (alerta crítico)
        """
        from apps.conversations.services import ConversationService
        from apps.automation.services import LLMOrchestratorService, UnifiedResponse
        from apps.automation.services.context_service import AutomationContextService

        payload = event.payload
        contact_info = payload.get('contact', {})

        if not message.conversation:
            try:
                conversation_service = ConversationService()
                conversation = conversation_service.get_or_create_conversation(
                    account=event.account,
                    phone_number=message.from_number,
                    contact_name=contact_info.get('profile', {}).get('name', '')
                )
                message.conversation = conversation
                message.save(update_fields=['conversation'])
            except Exception as exc:
                logger.error(f'[post_process] Failed to create conversation: {exc}')

        try:
            contact_name = contact_info.get('profile', {}).get('name', '')
            if message.conversation and contact_name and not message.conversation.contact_name:
                message.conversation.contact_name = contact_name
                message.conversation.save(update_fields=['contact_name', 'updated_at'])

            if message.conversation and message.text_body and not message.conversation.contact_name:
                extracted_name = self._extract_name_from_message(message.text_body)
                if extracted_name:
                    message.conversation.contact_name = extracted_name
                    message.conversation.save(update_fields=['contact_name', 'updated_at'])
                    logger.info(f'[post_process] Extracted name: {extracted_name}')
        except Exception as exc:
            logger.warning(f'[post_process] Error updating contact name: {exc}')

        context = AutomationContextService.resolve(
            account=event.account,
            conversation=message.conversation,
            create_profile=False,
        )
        llm_enabled = AutomationContextService.is_ai_enabled(
            context=context,
            conversation=message.conversation,
        )

        # Extrair dados de reply interativo (clique em botão / item de lista)
        _interactive_reply = None
        _location_data = None
        _msg_content = message.content or {}
        _interactive = _msg_content.get('interactive', {})
        if _interactive:
            if 'list_reply' in _interactive:
                _lr = _interactive['list_reply']
                _interactive_reply = {
                    'type': 'list_reply',
                    'id': _lr.get('id', ''),
                    'title': _lr.get('title', ''),
                }
            elif 'button_reply' in _interactive:
                _br = _interactive['button_reply']
                _interactive_reply = {
                    'type': 'button_reply',
                    'id': _br.get('id', ''),
                    'title': _br.get('title', ''),
                }
            if _interactive_reply:
                logger.info(
                    '[pipeline] Interactive reply detected: type=%s id=%s',
                    _interactive_reply['type'], _interactive_reply['id'],
                    extra={'pipeline.interactive_reply': True, 'message_id': str(message.id)},
                )

        # Extrair localização (mensagem de localização nativa do WhatsApp)
        _loc = _msg_content.get('location')
        if _loc:
            _lat = _loc.get('latitude')
            _lng = _loc.get('longitude')
            if _lat is not None and _lng is not None:
                _location_data = {
                    'lat': float(_lat),
                    'lng': float(_lng),
                    'address': _loc.get('address', ''),
                    'name': _loc.get('name', ''),
                }
                logger.info(
                    '[pipeline] Location message detected: lat=%.6f lng=%.6f',
                    _location_data['lat'], _location_data['lng'],
                    extra={'message_id': str(message.id)},
                )

        catalog_order_response = self._build_catalog_order_response(
            event=event,
            message=message,
            company_profile=context.profile,
            store=context.store,
        )
        if catalog_order_response:
            try:
                self._send_unified_interactive(event, message, catalog_order_response)
                if not message.processed_by_agent:
                    message.processed_by_agent = True
                    message.save(update_fields=['processed_by_agent'])
                logger.info(
                    '[pipeline] Catalog order handled deterministically',
                    extra={'pipeline.source': 'catalog_order', 'message_id': str(message.id)},
                )
                return
            except Exception as exc:
                logger.error(
                    '[pipeline] Failed to handle catalog order: %s',
                    exc,
                    exc_info=True,
                    extra={'message_id': str(message.id)},
                )

        # Human mode should suppress general bot chat, but it must not swallow
        # deterministic order events. Otherwise catalog orders and pending
        # delivery/payment steps never become StoreOrder rows in the panel.
        if message.conversation and message.conversation.mode == 'human':
            transactional_reply_ids = {
                'order_delivery',
                'order_pickup',
                'pay_pix',
                'pay_card',
                'pay_pickup',
            }
            reply_id = (_interactive_reply or {}).get('id', '')
            allow_transactional = (
                reply_id in transactional_reply_ids
                or reply_id.startswith('add_')
                or reply_id.startswith('product_')
                or bool(_location_data)
            )
            if not allow_transactional:
                logger.info(
                    '[pipeline] Conversation in human mode, skipping automation',
                    extra={'message_id': str(message.id)},
                )
                return
            logger.info(
                '[pipeline] Human mode bypass for deterministic order flow',
                extra={'message_id': str(message.id), 'reply_id': reply_id},
            )

        import threading
        import time as _time

        orchestrator_response = None
        orchestrator_error = None
        _t0 = _time.monotonic()

        def _run_orchestrator():
            nonlocal orchestrator_response, orchestrator_error
            try:
                service = LLMOrchestratorService(
                    account=event.account,
                    conversation=message.conversation,
                    use_llm=llm_enabled,
                    debug=False,
                )
                orchestrator_response = service.process_message(
                    message.text_body or '',
                    interactive_reply=_interactive_reply,
                    location_data=_location_data,
                )
                _source = getattr(getattr(orchestrator_response, 'source', None), 'value', 'unknown')
                logger.info(
                    '[pipeline] UnifiedService responded',
                    extra={'pipeline.source': _source, 'message_id': str(message.id)},
                )
            except Exception as exc:
                orchestrator_error = exc
                logger.warning(
                    '[pipeline] UnifiedService error: %s', exc,
                    extra={'pipeline.source': 'error', 'message_id': str(message.id)},
                )

        _orchestrator_timeout_s = max(30, int(getattr(settings, 'WHATSAPP_ORCHESTRATOR_TIMEOUT', 90)))

        _thread = threading.Thread(target=_run_orchestrator, daemon=True)
        _thread.start()
        _thread.join(timeout=_orchestrator_timeout_s)

        _orchestrator_ms = round((_time.monotonic() - _t0) * 1000, 1)
        _timed_out = _thread.is_alive()

        if _timed_out:
            orchestrator_error = TimeoutError(f'UnifiedService timeout after {_orchestrator_timeout_s}s')
            logger.warning(
                '[pipeline] UnifiedService timeout after %ss',
                _orchestrator_timeout_s,
                extra={'pipeline.timeout': True, 'message_id': str(message.id)},
            )

        # -- Tentar enviar resposta do orquestrador ----------------------------
        _response_sent = False

        if isinstance(orchestrator_response, UnifiedResponse) and not _timed_out:
            # Caminho A: resposta interativa (botões / lista)
            if orchestrator_response.buttons or orchestrator_response.interactive_type:
                try:
                    self._send_unified_interactive(event, message, orchestrator_response)
                    logger.info(
                        '[pipeline] Interactive response sent (%.0fms)', _orchestrator_ms,
                        extra={
                            'pipeline.source': getattr(getattr(orchestrator_response, 'source', None), 'value', 'handler'),
                            'pipeline.duration_ms': _orchestrator_ms,
                            'message_id': str(message.id),
                        },
                    )
                    _response_sent = True
                except Exception as exc:
                    orchestrator_error = exc
                    logger.error('[pipeline] Failed to send interactive: %s', exc, extra={'message_id': str(message.id)})

            # Caminho B: resposta de texto (enfileirada)
            if not _response_sent and orchestrator_response.content:
                try:
                    from ..tasks import send_agent_response
                    response_source = getattr(
                        getattr(orchestrator_response, 'source', None),
                        'value',
                        'handler',
                    )
                    send_agent_response.delay(
                        str(event.account.id),
                        message.from_number,
                        orchestrator_response.content,
                        str(message.whatsapp_message_id),
                        f'unified_{response_source}',
                    )
                    logger.info(
                        '[pipeline] Text response queued (%.0fms)', _orchestrator_ms,
                        extra={
                            'pipeline.source': response_source,
                            'pipeline.duration_ms': _orchestrator_ms,
                            'message_id': str(message.id),
                        },
                    )
                    _response_sent = True
                except Exception as exc:
                    orchestrator_error = exc
                    logger.error('[pipeline] Failed to queue text response: %s', exc, extra={'message_id': str(message.id)})

        # -- Fallback: agente LLM direto ---------------------------------------
        # Ativa quando: orquestrador não produziu resposta OU falhou / timed out
        if not _response_sent and not message.processed_by_agent:
            agent = AutomationContextService.get_default_agent(context=context)
            if llm_enabled and agent is not None:
                try:
                    current_app.send_task(
                        'apps.whatsapp.tasks.process_message_with_agent',
                        args=[str(message.id)],
                        queue='default',
                        countdown=0,
                    )
                    logger.info(
                        '[pipeline] Fallback agent enqueued',
                        extra={'pipeline.source': 'agent_fallback', 'message_id': str(message.id)},
                    )
                    _response_sent = True
                except Exception as exc:
                    logger.error('[pipeline] Failed to enqueue agent fallback: %s', exc, exc_info=True, extra={'message_id': str(message.id)})

        # -- Alerta crítico: mensagem sem resposta ------------------------------
        if not _response_sent:
            logger.error(
                '[pipeline] MESSAGE DROPPED — no response path succeeded. '
                'message_id=%s account=%s timed_out=%s orchestrator_error=%s',
                message.id, event.account.id, _timed_out, orchestrator_error,
                extra={'pipeline.dropped': True, 'message_id': str(message.id)},
            )

    def _build_catalog_order_response(self, event, message, company_profile=None, store=None):
        """Handle native WhatsApp catalog order payloads without involving the LLM."""
        order = (message.content or {}).get('order') or {}
        product_items = order.get('product_items') or []
        if not product_items:
            return None

        from apps.automation.services import UnifiedResponse
        from apps.automation.services.unified_service import ResponseSource
        from apps.automation.services import get_session_manager
        from apps.stores.models import StoreProduct

        if store is None:
            store = getattr(event.account, 'store', None)

        if not store:
            return UnifiedResponse(
                content=(
                    "Recebi seu pedido pelo catalogo, mas nao consegui identificar a loja agora. "
                    "Vou chamar um atendente para conferir."
                ),
                source=ResponseSource.HANDLER,
                metadata={'intent': 'catalog_order', 'error': 'store_not_found'},
            )

        retailer_ids = [
            str(item.get('product_retailer_id'))
            for item in product_items
            if item.get('product_retailer_id')
        ]
        products = {
            str(product.id): product
            for product in StoreProduct.objects.filter(
                store=store,
                id__in=retailer_ids,
                is_active=True,
            )
        }

        pending_items = []
        item_lines = []
        missing_items = []
        total = 0.0

        for item in product_items:
            product_id = str(item.get('product_retailer_id') or '')
            try:
                quantity = max(1, int(item.get('quantity') or 1))
            except (TypeError, ValueError):
                quantity = 1

            product = products.get(product_id)
            if not product:
                missing_items.append(product_id)
                continue

            product_price = float(product.price)
            unit_price = product_price
            meta_price = item.get('item_price')
            if meta_price is not None:
                try:
                    meta_price_float = float(meta_price)
                    if meta_price_float >= 0:
                        unit_price = meta_price_float
                    if abs(meta_price_float - product_price) >= 0.01:
                        logger.warning(
                            '[catalog_order] Meta catalog price differs from store price: '
                            'product=%s meta=%.2f store=%.2f',
                            product.id,
                            meta_price_float,
                            product_price,
                            extra={'message_id': str(message.id)},
                        )
                except (TypeError, ValueError):
                    pass

            pending_items.append({
                'product_id': str(product.id),
                'quantity': quantity,
                'unit_price': unit_price,
                'price_source': 'whatsapp_catalog',
            })
            line_total = unit_price * quantity
            total += line_total
            item_lines.append(f"• {quantity}x {product.name} - R$ {line_total:.2f}")

        if not pending_items:
            logger.warning(
                '[catalog_order] No matching products for catalog order: %s',
                missing_items,
                extra={'message_id': str(message.id)},
            )
            return UnifiedResponse(
                content=(
                    "Recebi seu pedido pelo catalogo, mas nao encontrei esses itens no sistema. "
                    "Vou chamar um atendente para conferir."
                ),
                source=ResponseSource.HANDLER,
                metadata={'intent': 'catalog_order', 'missing_items': missing_items},
            )

        try:
            session_manager = get_session_manager(company_profile or store or event.account, message.from_number)
            session_manager.save_pending_order_items(pending_items)
        except Exception as exc:
            logger.error(
                '[catalog_order] Failed to save pending items: %s',
                exc,
                exc_info=True,
                extra={'message_id': str(message.id)},
            )

        delivery_enabled = getattr(store, 'delivery_enabled', True)
        pickup_enabled = getattr(store, 'pickup_enabled', True)
        buttons = []
        if delivery_enabled:
            buttons.append({'id': 'order_delivery', 'title': '🛵 Entrega'})
        if pickup_enabled:
            buttons.append({'id': 'order_pickup', 'title': '🏪 Retirada'})
        if not buttons:
            buttons = [{'id': 'order_delivery', 'title': '🛵 Entrega'}]

        body = (
            "Recebi seu pedido pelo catalogo:\n\n"
            f"{chr(10).join(item_lines)}\n\n"
            f"Total dos itens: *R$ {total:.2f}*\n\n"
            "Como prefere receber?"
        )

        return UnifiedResponse(
            content=body,
            source=ResponseSource.HANDLER,
            buttons=buttons,
            metadata={
                'intent': 'catalog_order',
                'catalog_id': order.get('catalog_id'),
                'missing_items': missing_items,
            },
            interactive_type='buttons',
            interactive_data={'body': body, 'buttons': buttons},
        )

    def _is_llm_enabled_for_account(self, account: WhatsAppAccount, conversation=None) -> bool:
        from apps.automation.services.context_service import AutomationContextService

        context = AutomationContextService.resolve(
            account=account,
            conversation=conversation,
            create_profile=False,
        )
        return AutomationContextService.is_ai_enabled(
            context=context,
            conversation=conversation,
        )

    def _send_unified_interactive(self, event, message, unified_response) -> None:
        """Send interactive messages produced by the unified service."""
        from .message_service import MessageService

        svc = MessageService()
        account_id = str(event.account.id)
        interactive_data = unified_response.interactive_data or {}
        header = unified_response.header or interactive_data.get('header')
        footer = unified_response.footer or interactive_data.get('footer')

        if isinstance(header, str):
            header = {'type': 'text', 'text': header}

        if unified_response.interactive_type == 'product_list':
            try:
                svc.send_product_list(
                    account_id=account_id,
                    to=message.from_number,
                    sections=interactive_data.get('sections', []),
                    body_text=interactive_data.get('body') or unified_response.content,
                    catalog_id=interactive_data.get('catalog_id'),
                    header_text=header.get('text') if isinstance(header, dict) else header,
                    footer=footer,
                    reply_to=str(message.whatsapp_message_id),
                )
                return
            except Exception as exc:
                logger.warning(
                    '[pipeline] Product list send failed, falling back to WhatsApp list: %s',
                    exc,
                    extra={'message_id': str(message.id)},
                )
                fallback_sections = interactive_data.get('fallback_sections') or []
                if fallback_sections:
                    svc.send_interactive_list(
                        account_id=account_id,
                        to=message.from_number,
                        body_text=interactive_data.get('body') or unified_response.content,
                        button_text=interactive_data.get('button', 'Ver opcoes'),
                        sections=fallback_sections,
                        header=header.get('text') if isinstance(header, dict) else header,
                        footer=footer,
                        reply_to=str(message.whatsapp_message_id),
                    )
                    return

        if unified_response.interactive_type == 'list':
            svc.send_interactive_list(
                account_id=account_id,
                to=message.from_number,
                body_text=interactive_data.get('body') or unified_response.content,
                button_text=interactive_data.get('button', 'Ver opcoes'),
                sections=interactive_data.get('sections', []),
                header=header.get('text') if isinstance(header, dict) else header,
                footer=footer,
                reply_to=str(message.whatsapp_message_id),
            )
            return

        if unified_response.interactive_type == 'buttons' or unified_response.buttons:
            svc.send_interactive_buttons(
                account_id=account_id,
                to=message.from_number,
                body_text=interactive_data.get('body') or unified_response.content,
                buttons=interactive_data.get('buttons') or unified_response.buttons or [],
                header=header,
                footer=footer,
                reply_to=str(message.whatsapp_message_id),
            )
            return

        svc.send_text_message(
            account_id=account_id,
            to=message.from_number,
            text=unified_response.content,
            reply_to=str(message.whatsapp_message_id),
        )
    def _extract_name_from_message(self, text: str) -> str:
        """Extract name from message patterns like 'my name is John', 'sou o Carlos', etc."""
        import re
        
        text_lower = text.lower().strip()
        
        # Patterns to match name introductions
        patterns = [
            r'meu nome [Ã©|e]\s+(.+)',
            r'meu nome eh\s+(.+)',
            r'sou (?:o|a)\s+(.+)',
            r'(?:o|a) meu nome [Ã©|e]\s+(.+)',
            r'pode me chamar de\s+(.+)',
            r'(?:eu sou|sou)\s+(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).strip()
                # Remove punctuation at the end
                name = re.sub(r'[.!?;,]$', '', name)
                # Capitalize first letter of each word
                name = name.title()
                if len(name) > 1 and len(name) < 50:  # Reasonable name length
                    return name
        
        return ""

    def _process_inbound_message(self, event: WebhookEvent) -> Optional[Message]:
        """Process an inbound message event."""
        payload = event.payload
        message_data = payload.get('message', {})
        contact_data = payload.get('contact', {})
        
        if not message_data:
            logger.warning(f"No message data in event {event.id}")
            return None
        
        # Extract message details
        whatsapp_message_id = message_data.get('id')
        from_number = message_data.get('from')
        timestamp = message_data.get('timestamp')
        message_type = message_data.get('type', 'unknown')
        
        # Check for duplicate message
        existing = Message.objects.filter(whatsapp_message_id=whatsapp_message_id).first()
        if existing:
            logger.info(f"Duplicate message ignored: {whatsapp_message_id}")
            return existing
        
        # Extract text content based on message type
        text_body = ''
        content = {}
        media_id = ''
        media_url = ''
        media_mime_type = ''
        media_sha256 = ''
        
        if message_type == 'text':
            text_body = message_data.get('text', {}).get('body', '')
            content = {'text': text_body}
        elif message_type in ['image', 'video', 'audio', 'document', 'sticker']:
            media_data = message_data.get(message_type, {})
            media_id = media_data.get('id', '')
            media_mime_type = media_data.get('mime_type', '')
            text_body = media_data.get('caption', '')
            content = {message_type: media_data}
            media_url, media_sha256 = self._fetch_and_store_media(event.account, media_id, media_mime_type)
        elif message_type == 'location':
            location = message_data.get('location', {})
            content = {'location': location}
            location_label = location.get('name') or location.get('address') or 'Localizacao'
            text_body = f"\U0001f4cd {location_label}"
        elif message_type == 'contacts':
            contacts = message_data.get('contacts', [])
            content = {'contacts': contacts}
            text_body = f"\U0001f464 {len(contacts)} contato(s)"
        elif message_type == 'interactive':
            interactive = message_data.get('interactive', {})
            content = {'interactive': interactive}
            # Extract button/list reply
            if 'button_reply' in interactive:
                text_body = interactive['button_reply'].get('title', '')
            elif 'list_reply' in interactive:
                text_body = interactive['list_reply'].get('title', '')
        elif message_type == 'button':
            button = message_data.get('button', {})
            text_body = button.get('text', '')
            content = {'button': button}
        elif message_type == 'reaction':
            reaction = message_data.get('reaction', {})
            content = {'reaction': reaction}
            text_body = reaction.get('emoji', 'ðŸ‘')
        elif message_type == 'order':
            order = message_data.get('order', {})
            content = {'order': order}
            text_body = f"ðŸ›’ Order with {len(order.get('product_items', []))} item(s)"
        else:
            content = message_data

        logger.info(
            "[_process_inbound_message] Parsed inbound payload: type=%s text_len=%s context_id=%s",
            message_type,
            len(text_body or ''),
            message_data.get('context', {}).get('id', ''),
        )
        if message_type in {'text', 'interactive', 'button'} and not (text_body or '').strip():
            logger.warning(
                "[_process_inbound_message] Inbound message has empty text_body: type=%s message_id=%s",
                message_type,
                whatsapp_message_id,
            )
        
        # Get or create conversation
        logger.info(f"[_process_inbound_message] About to create conversation: account={event.account.id}, phone={from_number}, contact_name={contact_data.get('profile', {}).get('name', '')}")
        try:
            conversation = self._get_or_create_conversation(
                account=event.account,
                phone_number=from_number,
                contact_name=contact_data.get('profile', {}).get('name', '')
            )
            contact_update_fields = []
            wa_id = contact_data.get('wa_id') or ''
            profile_name = contact_data.get('profile', {}).get('name', '')
            if wa_id and conversation.wa_id != wa_id:
                conversation.wa_id = wa_id
                contact_update_fields.append('wa_id')
            if profile_name and conversation.contact_name != profile_name:
                conversation.contact_name = profile_name
                conversation.profile_name_last_seen_at = timezone.now()
                contact_update_fields.extend(['contact_name', 'profile_name_last_seen_at'])
            elif profile_name:
                conversation.profile_name_last_seen_at = timezone.now()
                contact_update_fields.append('profile_name_last_seen_at')
            if contact_update_fields:
                conversation.save(update_fields=list(dict.fromkeys(contact_update_fields + ['updated_at'])))
            logger.info(f"[_process_inbound_message] Conversation created/retrieved: id={conversation.id}")
        except Exception as conv_error:
            logger.error(f"[_process_inbound_message] Failed to create conversation: {conv_error}", exc_info=True)
            raise
        
        # Create message
        message = Message.objects.create(
            account=event.account,
            conversation=conversation,
            whatsapp_message_id=whatsapp_message_id,
            direction=Message.MessageDirection.INBOUND,
            message_type=self._map_message_type(message_type),
            status=Message.MessageStatus.DELIVERED,
            from_number=from_number,
            to_number=event.account.phone_number,
            content=content,
            text_body=text_body,
            media_id=media_id,
            media_url=media_url,
            media_mime_type=media_mime_type,
            media_sha256=media_sha256,
            context_message_id=message_data.get('context', {}).get('id', ''),
            delivered_at=timezone.now(),
            metadata={
                'timestamp': timestamp,
                'contact': contact_data
            }
        )
        
        # Link event to message
        event.related_message = message
        event.save(update_fields=['related_message'])
        
        # Update conversation
        conversation.last_message_at = timezone.now()
        conversation.last_customer_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at', 'last_customer_message_at', 'updated_at'])
        
        # Broadcast to connected clients
        self._broadcast_new_message(event.account, message, conversation, contact_data)
        
        logger.info(f"Processed inbound message: {message.id} from {from_number}")
        return message

    def _process_status_update(self, event: WebhookEvent) -> Optional[Message]:
        """Process a message status update event."""
        payload = event.payload
        
        whatsapp_message_id = payload.get('id')
        status = payload.get('status')
        timestamp = payload.get('timestamp')
        recipient_id = payload.get('recipient_id')
        
        if not whatsapp_message_id or not status:
            logger.warning(f"Invalid status update in event {event.id}")
            return None
        
        # Find the message
        message = Message.objects.filter(whatsapp_message_id=whatsapp_message_id).first()
        
        if not message:
            logger.warning(f"Message not found for status update: {whatsapp_message_id}")
            return None
        
        # Map Meta status to our status
        status_map = {
            'sent': Message.MessageStatus.SENT,
            'delivered': Message.MessageStatus.DELIVERED,
            'read': Message.MessageStatus.READ,
            'failed': Message.MessageStatus.FAILED,
        }
        
        new_status = status_map.get(status)
        if not new_status:
            logger.warning(f"Unknown status: {status}")
            return message
        
        # Only update if status is "higher" (sent < delivered < read)
        status_order = ['pending', 'sent', 'delivered', 'read', 'failed']
        current_idx = status_order.index(message.status) if message.status in status_order else 0
        new_idx = status_order.index(new_status) if new_status in status_order else 0
        
        if new_idx <= current_idx and new_status != 'failed':
            logger.debug(f"Ignoring status update {status} for message {message.id} (current: {message.status})")
            return message
        
        # Update message status
        message.status = new_status
        update_fields = ['status', 'updated_at']
        
        # Set timestamp fields
        status_time = timezone.now()
        if timestamp:
            try:
                status_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            except (ValueError, TypeError):
                pass
        
        if new_status == Message.MessageStatus.SENT:
            message.sent_at = status_time
            update_fields.append('sent_at')
        elif new_status == Message.MessageStatus.DELIVERED:
            message.delivered_at = status_time
            update_fields.append('delivered_at')
        elif new_status == Message.MessageStatus.READ:
            message.read_at = status_time
            update_fields.append('read_at')
        elif new_status == Message.MessageStatus.FAILED:
            message.failed_at = status_time
            update_fields.append('failed_at')
            # Extract error info if available
            errors = payload.get('errors', [])
            if errors:
                message.error_code = str(errors[0].get('code', ''))
                message.error_message = errors[0].get('title', '')
                update_fields.extend(['error_code', 'error_message'])
        
        message.save(update_fields=update_fields)
        
        # Link event to message
        event.related_message = message
        event.save(update_fields=['related_message'])
        
        # Broadcast status update
        self.broadcast.broadcast_status_update(
            account_id=str(event.account.id),
            message_id=str(message.id),
            status=new_status,
            whatsapp_message_id=whatsapp_message_id,
            timestamp=status_time
        )
        
        logger.info(f"Updated message {message.id} status to {new_status}")
        return message

    def _process_error(self, event: WebhookEvent) -> None:
        """Process an error event."""
        payload = event.payload
        
        error_code = str(payload.get('code', ''))
        error_title = payload.get('title', 'Unknown error')
        error_message = payload.get('message', '')
        error_details = payload.get('error_data', {})
        
        logger.error(f"WhatsApp API error: {error_code} - {error_title}: {error_message}")
        
        # Broadcast error to clients
        self.broadcast.broadcast_error(
            account_id=str(event.account.id),
            error_code=error_code,
            error_message=f"{error_title}: {error_message}" if error_message else error_title
        )

    def _get_or_create_conversation(
        self,
        account: WhatsAppAccount,
        phone_number: str,
        contact_name: str = ''
    ):
        """Get or create a conversation for a phone number.
        
        Uses transaction-safe approach to handle race conditions where multiple
        webhook events try to create a conversation for the same phone number simultaneously.
        """
        from apps.conversations.models import Conversation
        from django.db import IntegrityError
        phone_number = normalize_phone_number(phone_number)
        logger.info(f"[_get_or_create_conversation] START - account={account.id}, phone={phone_number}, contact_name={contact_name}")
        
        try:
            logger.info(f"[_get_or_create_conversation] Calling get_or_create...")
            conversation, created = Conversation.objects.get_or_create(
                account=account,
                phone_number=phone_number,
                defaults={
                    'contact_name': contact_name,
                    'status': Conversation.ConversationStatus.OPEN,
                    'mode': Conversation.ConversationMode.AUTO
                }
            )
            
            if created:
                logger.info(f"[_get_or_create_conversation] NEW conversation created: {conversation.id}")
                # Broadcast new conversation
                self.broadcast.broadcast_conversation_update(
                    account_id=str(account.id),
                    conversation={
                        'id': str(conversation.id),
                        'phone_number': phone_number,
                        'contact_name': contact_name,
                        'wa_id': '',
                        'profile_picture': '',
                        'profile_picture_url': '',
                        'status': conversation.status,
                        'mode': conversation.mode,
                        'created_at': conversation.created_at.isoformat()
                    }
                )
            else:
                logger.info(f"[_get_or_create_conversation] EXISTING conversation retrieved: {conversation.id}")
            
            if contact_name and not conversation.contact_name:
                # Update contact name if we didn't have it
                logger.info(f"[_get_or_create_conversation] Updating contact_name to: {contact_name}")
                conversation.contact_name = contact_name
                conversation.save(update_fields=['contact_name', 'updated_at'])
            
            logger.info(f"[_get_or_create_conversation] SUCCESS - returning conversation: {conversation.id}")
            return conversation
            
        except IntegrityError as ie:
            # Race condition: another request created the conversation first
            # This can happen with unique_together constraint on (account, phone_number)
            logger.warning(f"[_get_or_create_conversation] IntegrityError on get_or_create for {phone_number}: {ie}, retrying get...")
            try:
                conversation = Conversation.objects.get(
                    account=account,
                    phone_number=phone_number
                )
                logger.info(f"[_get_or_create_conversation] Retrieved after IntegrityError: {conversation.id}")
                return conversation
            except Conversation.DoesNotExist:
                # This shouldn't happen but handle it gracefully
                logger.error(f"[_get_or_create_conversation] Conversation not found after IntegrityError for {phone_number}")
                raise
        except Exception as e:
            logger.error(f"[_get_or_create_conversation] Unexpected error: {e}", exc_info=True)
            raise

    def _broadcast_new_message(
        self,
        account: WhatsAppAccount,
        message: Message,
        conversation,
        contact_data: Dict[str, Any]
    ) -> None:
        """Broadcast a new message to connected clients."""
        message_dict = {
            'id': str(message.id),
            'whatsapp_message_id': message.whatsapp_message_id,
            'direction': message.direction,
            'message_type': message.message_type,
            'status': message.status,
            'from_number': message.from_number,
            'to_number': message.to_number,
            'text_body': message.text_body,
            'content': message.content,
            'media_id': message.media_id,
            'media_url': message.media_url,
            'media_mime_type': message.media_mime_type,
            'media_sha256': message.media_sha256,
            'created_at': message.created_at.isoformat(),
            'delivered_at': message.delivered_at.isoformat() if message.delivered_at else None,
        }
        
        contact_dict = {
            'wa_id': contact_data.get('wa_id', message.from_number),
            'name': contact_data.get('profile', {}).get('name', ''),
        }
        
        self.broadcast.broadcast_new_message(
            account_id=str(account.id),
            message=message_dict,
            conversation_id=str(conversation.id) if conversation else None,
            contact=contact_dict
        )

    def _map_message_type(self, meta_type: str) -> str:
        """Map Meta message type to our MessageType."""
        type_map = {
            'text': Message.MessageType.TEXT,
            'image': Message.MessageType.IMAGE,
            'video': Message.MessageType.VIDEO,
            'audio': Message.MessageType.AUDIO,
            'document': Message.MessageType.DOCUMENT,
            'sticker': Message.MessageType.STICKER,
            'location': Message.MessageType.LOCATION,
            'contacts': Message.MessageType.CONTACTS,
            'interactive': Message.MessageType.INTERACTIVE,
            'template': Message.MessageType.TEMPLATE,
            'reaction': Message.MessageType.REACTION,
            'button': Message.MessageType.BUTTON,
            'order': Message.MessageType.ORDER,
            'system': Message.MessageType.SYSTEM,
        }
        return type_map.get(meta_type, Message.MessageType.UNKNOWN)

    def _fetch_and_store_media(
        self,
        account: WhatsAppAccount,
        media_id: str,
        mime_type: str
    ) -> Tuple[str, str]:
        """Download media from WhatsApp and store it locally or on the configured storage."""
        if not media_id:
            return '', ''

        try:
            api_service = WhatsAppAPIService(account)
            url = api_service.get_media_url(media_id)
            if not url:
                return '', ''

            media_bytes = api_service.download_media(url)
            sha256 = hashlib.sha256(media_bytes).hexdigest()
            extension = mime_to_extension(mime_type)
            filename = f"whatsapp/{account.id}/{media_id}{extension}"

            if default_storage.exists(filename):
                return build_absolute_media_url(default_storage.url(filename)), sha256

            saved_path = default_storage.save(filename, ContentFile(media_bytes))
            return build_absolute_media_url(default_storage.url(saved_path)), sha256

        except Exception as exc:
            logger.warning(f"Failed to persist media {media_id}: {exc}")
            return '', ''
