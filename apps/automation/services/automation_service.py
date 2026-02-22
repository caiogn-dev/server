# -*- coding: utf-8 -*-
"""
Automation Service - Core business logic for message automation.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationError
from apps.whatsapp.models import WhatsAppAccount, Message
from apps.whatsapp.services import MessageService as WhatsAppService
from apps.conversations.models import Conversation
from apps.agents.services import AgentService

from ..models import CompanyProfile, AutoMessage, CustomerSession, AutomationLog

logger = logging.getLogger(__name__)


class AutomationService:
    """Service for handling automated responses and notifications."""

    def __init__(self):
        self.whatsapp_service = WhatsAppService()

    # ==================== Company Profile ====================

    def get_company_profile(self, account_id: str) -> Optional[CompanyProfile]:
        """Get company profile by WhatsApp account ID."""
        try:
            return CompanyProfile.objects.select_related('account').get(
                account_id=account_id,
                is_active=True
            )
        except CompanyProfile.DoesNotExist:
            return None

    def create_company_profile(
        self,
        account_id: str = None,
        store_id: str = None,
        company_name: str = None,
        business_type: str = 'other',
        website_url: str = '',
        menu_url: str = '',
        **kwargs
    ) -> CompanyProfile:
        """Create a new company profile."""
        from apps.stores.models import Store
        
        store = None
        account = None
        
        # If store_id provided, get store and its account
        if store_id:
            try:
                store = Store.objects.get(id=store_id, is_active=True)
                if store.whatsapp_account:
                    account = store.whatsapp_account
            except Store.DoesNotExist:
                raise NotFoundError(message="Store not found")
        
        # If account_id provided, get account
        if account_id:
            try:
                account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
            except WhatsAppAccount.DoesNotExist:
                raise NotFoundError(message="WhatsApp account not found")
        
        # Must have at least store or account
        if not store and not account:
            raise ValidationError(message="Either store_id or account_id must be provided")
        
        # Check if profile already exists for account
        if account and hasattr(account, 'company_profile') and account.company_profile:
            raise ValidationError(message="Company profile already exists for this account")
        
        # Check if profile already exists for store
        if store and hasattr(store, 'automation_profile') and store.automation_profile:
            raise ValidationError(message="Company profile already exists for this store")
        
        # Use store name if company_name not provided
        if not company_name and store:
            company_name = store.name
        
        if not company_name:
            company_name = account.name if account else 'Minha Empresa'

        profile = CompanyProfile.objects.create(
            account=account,
            store=store,
            _company_name=company_name,
            _business_type=business_type,
            website_url=website_url,
            menu_url=menu_url,
            **kwargs
        )

        # Generate API key and webhook secret
        profile.generate_api_key()
        profile.generate_webhook_secret()

        # Create default auto messages
        self._create_default_auto_messages(profile)

        logger.info(f"Company profile created: {profile.company_name}")
        return profile

    def update_company_profile(
        self,
        profile_id: str,
        **kwargs
    ) -> CompanyProfile:
        """Update company profile."""
        try:
            profile = CompanyProfile.objects.get(id=profile_id, is_active=True)
        except CompanyProfile.DoesNotExist:
            raise NotFoundError(message="Company profile not found")

        # Handle business_hours specially - if linked to Store, update Store instead
        business_hours = kwargs.pop('business_hours', None)
        if business_hours is not None:
            if profile.store_id:
                # Update Store operating_hours instead
                profile.store.operating_hours = business_hours
                profile.store.save(update_fields=['operating_hours', 'updated_at'])
                logger.info(f"Updated Store operating_hours for {profile.store.name}")
            else:
                # Update profile's internal field
                profile._business_hours = business_hours
        
        # Handle fields that map to Store when linked
        if profile.store_id:
            # These fields should update the Store if linked
            store_fields = ['company_name', 'description']
            store_updates = {}
            
            for field in store_fields:
                if field in kwargs:
                    value = kwargs.pop(field)
                    if field == 'company_name':
                        store_updates['name'] = value
                    else:
                        store_updates[field] = value
            
            if store_updates:
                for key, value in store_updates.items():
                    setattr(profile.store, key, value)
                profile.store.save(update_fields=list(store_updates.keys()) + ['updated_at'])
                logger.info(f"Updated Store fields for {profile.store.name}")

        # Handle ForeignKey fields that receive UUIDs
        fk_fields = ['default_agent']
        for fk_field in fk_fields:
            if fk_field in kwargs:
                fk_value = kwargs.pop(fk_field)
                if fk_value:
                    # Set using _id suffix for ForeignKey
                    setattr(profile, f'{fk_field}_id', fk_value)
                else:
                    setattr(profile, f'{fk_field}_id', None)

        # Update remaining fields on profile
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.save()
        logger.info(f"Company profile updated: {profile.company_name}")
        return profile

    def _create_default_auto_messages(self, profile: CompanyProfile):
        """Create default auto messages for a new company profile."""
        self.ensure_auto_messages(profile)

    def ensure_auto_messages(self, profile: CompanyProfile, force: bool = False) -> Dict[str, int]:
        """Ensure default auto messages exist for a company profile."""
        created = 0
        replaced = 0
        templates = self._get_default_auto_messages(profile)

        for template in templates:
            existing = AutoMessage.objects.filter(
                company=profile,
                event_type=template['event_type'],
                name=template['name']
            )

            if force and existing.exists():
                replaced += existing.count()
                existing.delete()

            auto_message, was_created = AutoMessage.objects.get_or_create(
                company=profile,
                event_type=template['event_type'],
                name=template['name'],
                defaults={
                    'message_text': template['message_text'],
                    'media_url': template.get('media_url', ''),
                    'media_type': template.get('media_type', ''),
                    'buttons': template.get('buttons', []),
                    'delay_seconds': template.get('delay_seconds', 0),
                    'priority': template.get('priority', 100),
                    'is_active': template.get('is_active', True),
                    'conditions': template.get('conditions', {}),
                }
            )

            if was_created:
                created += 1

        return {'created': created, 'replaced': replaced}

    def _get_default_auto_messages(self, profile: CompanyProfile) -> List[Dict[str, Any]]:
        """Return the default auto message templates."""
        menu_link = profile.menu_url or profile.website_url or 'https://pastita.com.br/cardapio'
        company_name = profile.company_name or 'nosso time'
        cart_delay = max(60, profile.abandoned_cart_delay_minutes * 60)

        return [
            {
                'event_type': AutoMessage.EventType.WELCOME,
                'name': 'Boas-vindas principal',
                'message_text': (
                    "Olá {customer_name}! 👋\n\n"
                    f"Bem-vindo(a) à *{company_name}*!\n"
                    "Como posso ajudar você hoje?"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.MENU,
                'name': 'Envio automático do cardápio',
                'message_text': (
                    "📋 Aqui está nosso cardápio/catálogo:\n"
                    f"{menu_link}\n\n"
                    "Qualquer dúvida, basta responder aqui."
                ),
                'priority': 2,
            },
            {
                'event_type': AutoMessage.EventType.OUT_OF_HOURS,
                'name': 'Mensagem fora do horário',
                'message_text': (
                    f"Obrigado por entrar em contato com a *{company_name}*.\n\n"
                    "No momento estamos fora do horário de atendimento.\n"
                    "Responderemos o mais breve possível!"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.CART_ABANDONED,
                'name': 'Carrinho abandonado',
                'message_text': (
                    "Oi {customer_name}! 🛒\n\n"
                    "Percebi que você deixou alguns itens no carrinho.\n"
                    "Total: *R$ {cart_total}*.\n\n"
                    "Deseja finalizar agora com um cupom especial?"
                ),
                'delay_seconds': cart_delay,
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.PIX_GENERATED,
                'name': 'PIX gerado',
                'message_text': (
                    "💰 *PIX Gerado!*\n\n"
                    "Pedido: #{order_number}\n"
                    "Valor: *R$ {amount}*.\n\n"
                    "Você quer receber o código aqui ou gerar um novo?"
                ),
                'buttons': [
                    {'id': 'send_pix', 'title': '📱 Receber código'},
                    {'id': 'new_pix', 'title': '🔄 Gerar novo PIX'},
                ],
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.PIX_REMINDER,
                'name': 'Lembrete PIX',
                'message_text': (
                    "⏰ O pagamento PIX ainda não foi confirmado.\n\n"
                    "Valor: *R$ {amount}*.\n"
                    "Quer que eu envie o código de novo?"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.PIX_EXPIRED,
                'name': 'PIX expirado',
                'message_text': (
                    "⚠️ O código PIX expirou.\n\n"
                    "Deseja gerar um novo pagamento agora?"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.PAYMENT_CONFIRMED,
                'name': 'Pagamento confirmado',
                'message_text': (
                    "✅ Pagamento confirmado!\n\n"
                    "Pedido: #{order_number}\n"
                    "Valor: R$ {amount}.\n\n"
                    "Seu pedido já está sendo preparado."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.PAYMENT_FAILED,
                'name': 'Pagamento falhou',
                'message_text': (
                    "❌ O pagamento não foi identificado.\n\n"
                    "Deseja gerar outro PIX ou pagar por cartão?"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_CONFIRMED,
                'name': 'Pedido confirmado',
                'message_text': (
                    "🎉 Pedido confirmado!\n\n"
                    "Pedido #{order_number} está confirmado e já entrou na fila."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_PREPARING,
                'name': 'Pedido em preparo',
                'message_text': (
                    "👨‍🍳 Estamos preparando seu pedido #{order_number}.\n\n"
                    "Em breve estará a caminho!"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_READY,
                'name': 'Pedido pronto',
                'message_text': (
                    "⏱️ Pedido #{order_number} pronto para retirada.\n\n"
                    "Aguarde a chegada do entregador ou venha buscar!"
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_SHIPPED,
                'name': 'Pedido enviado',
                'message_text': (
                    "🚚 Pedido #{order_number} saiu para entrega!\n\n"
                    "Rastreio: {tracking_code}.\n"
                    "Previsão: {delivery_estimate}."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_OUT_FOR_DELIVERY,
                'name': 'Saiu para entrega',
                'message_text': (
                    "📍 Pedido #{order_number} está a caminho!\n\n"
                    "Fique atento ao entregador."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_DELIVERED,
                'name': 'Pedido entregue',
                'message_text': (
                    "🍽️ Pedido #{order_number} entregue!\n\n"
                    "Esperamos que aproveite e conte com a gente sempre."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.ORDER_CANCELLED,
                'name': 'Pedido cancelado',
                'message_text': (
                    "🛑 Pedido #{order_number} foi cancelado.\n\n"
                    "Se precisar de ajuda, fale conosco aqui."
                ),
                'priority': 1,
            },
            {
                'event_type': AutoMessage.EventType.FEEDBACK_REQUEST,
                'name': 'Solicitar avaliação',
                'message_text': (
                    "💬 Oi {customer_name}, gostaríamos de saber como foi.\n\n"
                    "Você pode responder esta mensagem com sua avaliação?"
                ),
                'priority': 2,
            },
        ]

    # ==================== Message Handling ====================

    def handle_incoming_message(
        self,
        account_id: str,
        from_number: str,
        message_text: str,
        message_type: str = 'text',
        message_data: Dict = None
    ) -> Optional[str]:
        """
        Handle an incoming message and generate automatic response.
        Returns the response message or None if no auto-response.
        """
        profile = self.get_company_profile(account_id)
        if not profile or not profile.auto_reply_enabled:
            return None

        # Log the incoming message
        self._log_action(
            profile,
            AutomationLog.ActionType.MESSAGE_RECEIVED,
            f"Message received from {from_number}",
            phone_number=from_number,
            request_data={'text': message_text, 'type': message_type}
        )

        # Get or create customer session
        session = self._get_or_create_session(profile, from_number)

        # Check if it's a button response
        if message_type == 'interactive' and message_data:
            return self._handle_button_response(profile, session, message_data)

        # Check business hours
        if not self._is_within_business_hours(profile):
            return self._send_auto_message(profile, session, AutoMessage.EventType.OUT_OF_HOURS)

        # Check if this is first message (welcome)
        conversation = self._get_conversation(account_id, from_number)
        if conversation and self._is_first_message(conversation):
            response = self._send_auto_message(profile, session, AutoMessage.EventType.WELCOME)
            
            # Also send menu if enabled
            if profile.menu_auto_send and profile.menu_url:
                menu_response = self._send_auto_message(profile, session, AutoMessage.EventType.MENU)
                if menu_response:
                    response = f"{response}\n\n{menu_response}" if response else menu_response
            
            return response

        # If AI Agent is enabled, use it for complex responses
        if profile.use_ai_agent and profile.default_agent:
            return self._process_with_agent(profile, session, message_text)

        # Default: no auto-response for regular messages
        return None

    def _handle_button_response(
        self,
        profile: CompanyProfile,
        session: CustomerSession,
        message_data: Dict
    ) -> Optional[str]:
        """Handle interactive button responses."""
        button_id = message_data.get('button_reply', {}).get('id', '')
        
        if button_id == 'send_pix':
            # Send PIX code
            if session.pix_code:
                return f"📱 *Código PIX Copia e Cola:*\n\n```{session.pix_code}```"
            return "Desculpe, não encontrei um código PIX ativo. Por favor, gere um novo no site."
        
        elif button_id == 'new_pix':
            return f"🔄 Para gerar um novo PIX, acesse:\n\n{profile.order_url or profile.website_url}"
        
        return None

    def _is_within_business_hours(self, profile: CompanyProfile) -> bool:
        """Check if current time is within business hours."""
        if not profile.business_hours:
            return True  # No hours defined = always open
        
        now = timezone.localtime()
        day_name = now.strftime('%A').lower()
        
        day_hours = profile.business_hours.get(day_name, {})
        if not day_hours or not day_hours.get('open'):
            return False
        
        try:
            open_time = datetime.strptime(day_hours.get('start', '00:00'), '%H:%M').time()
            close_time = datetime.strptime(day_hours.get('end', '23:59'), '%H:%M').time()
            return open_time <= now.time() <= close_time
        except (ValueError, TypeError):
            return True

    def _is_first_message(self, conversation: Conversation) -> bool:
        """Check if this is the first message in the conversation."""
        return Message.objects.filter(
            conversation=conversation,
            direction='inbound'
        ).count() <= 1

    def _get_conversation(self, account_id: str, phone_number: str) -> Optional[Conversation]:
        """Get conversation for a phone number."""
        try:
            return Conversation.objects.get(
                account_id=account_id,
                phone_number=phone_number,
                is_active=True
            )
        except Conversation.DoesNotExist:
            return None

    def _process_with_agent(
        self,
        profile: CompanyProfile,
        session: CustomerSession,
        message_text: str
    ) -> Optional[str]:
        """Process message with AI Agent (Langchain)."""
        try:
            from apps.agents.services import LangchainService
            
            agent = profile.default_agent
            if not agent:
                return None
            
            service = LangchainService(agent)
            result = service.process_message(
                message=message_text,
                session_id=session.session_id,
                phone_number=session.phone_number,
                conversation_id=str(session.id) if hasattr(session, 'id') else None
            )
            return result.get('response')
        except Exception as e:
            logger.error(f"AI Agent error: {str(e)}")
            return None

    # ==================== Customer Sessions ====================

    def _get_or_create_session(
        self,
        profile: CompanyProfile,
        phone_number: str
    ) -> CustomerSession:
        """Get or create a customer session."""
        import uuid
        
        session, created = CustomerSession.objects.get_or_create(
            company=profile,
            phone_number=phone_number,
            status__in=[
                CustomerSession.SessionStatus.ACTIVE,
                CustomerSession.SessionStatus.CART_CREATED,
                CustomerSession.SessionStatus.PAYMENT_PENDING,
            ],
            defaults={
                'session_id': str(uuid.uuid4()),
            }
        )
        
        if created:
            self._log_action(
                profile,
                AutomationLog.ActionType.SESSION_CREATED,
                f"Session created for {phone_number}",
                phone_number=phone_number,
                session=session
            )
        
        return session

    def get_session_by_id(self, session_id: str) -> Optional[CustomerSession]:
        """Get session by session ID."""
        try:
            return CustomerSession.objects.select_related('company').get(
                session_id=session_id,
                is_active=True
            )
        except CustomerSession.DoesNotExist:
            return None

    def get_session_by_phone(
        self,
        company_id: str,
        phone_number: str
    ) -> Optional[CustomerSession]:
        """Get active session by phone number."""
        return CustomerSession.objects.filter(
            company_id=company_id,
            phone_number=phone_number,
            is_active=True
        ).exclude(
            status__in=[
                CustomerSession.SessionStatus.COMPLETED,
                CustomerSession.SessionStatus.EXPIRED
            ]
        ).first()

    # ==================== External Events (Webhooks) ====================

    def handle_cart_event(
        self,
        api_key: str,
        session_id: str,
        event_type: str,
        cart_data: Dict
    ) -> bool:
        """Handle cart events from external site."""
        profile = self._validate_api_key(api_key)
        if not profile:
            return False

        session = self.get_session_by_id(session_id)
        if not session:
            # Create new session
            phone_number = cart_data.get('phone_number', '')
            if not phone_number:
                logger.warning("Cart event without phone number")
                return False
            
            session = CustomerSession.objects.create(
                company=profile,
                phone_number=phone_number,
                session_id=session_id,
                customer_name=cart_data.get('customer_name', ''),
                customer_email=cart_data.get('customer_email', ''),
            )

        # Update session with cart data
        session.cart_data = cart_data.get('items', [])
        session.cart_total = cart_data.get('total', 0)
        session.cart_items_count = cart_data.get('items_count', 0)
        session.external_customer_id = cart_data.get('customer_id', '')

        if event_type == 'cart_created':
            session.status = CustomerSession.SessionStatus.CART_CREATED
            session.cart_created_at = timezone.now()
        elif event_type == 'cart_updated':
            session.cart_updated_at = timezone.now()
        elif event_type == 'cart_abandoned':
            session.status = CustomerSession.SessionStatus.CART_ABANDONED
            # Schedule abandoned cart notification
            self._schedule_abandoned_cart_notification(profile, session)

        session.save()

        self._log_action(
            profile,
            AutomationLog.ActionType.WEBHOOK_RECEIVED,
            f"Cart event: {event_type}",
            phone_number=session.phone_number,
            session=session,
            event_type=event_type,
            request_data=cart_data
        )

        return True

    def handle_payment_event(
        self,
        api_key: str,
        session_id: str,
        event_type: str,
        payment_data: Dict
    ) -> bool:
        """Handle payment events from external site."""
        profile = self._validate_api_key(api_key)
        if not profile:
            return False

        session = self.get_session_by_id(session_id)
        if not session:
            logger.warning(f"Payment event for unknown session: {session_id}")
            return False

        if event_type == 'pix_generated':
            session.pix_code = payment_data.get('pix_code', '')
            session.pix_qr_code = payment_data.get('qr_code', '')
            session.pix_expires_at = payment_data.get('expires_at')
            session.payment_id = payment_data.get('payment_id', '')
            session.status = CustomerSession.SessionStatus.PAYMENT_PENDING
            session.save()

            # Send PIX notification
            if profile.pix_notification_enabled:
                self._send_notification(
                    profile,
                    session,
                    AutoMessage.EventType.PIX_GENERATED,
                    {
                        'amount': payment_data.get('amount', session.cart_total),
                        'order_number': payment_data.get('order_number', ''),
                    }
                )

        elif event_type == 'payment_confirmed':
            session.status = CustomerSession.SessionStatus.PAYMENT_CONFIRMED
            session.save()

            # Send payment confirmation
            if profile.payment_confirmation_enabled:
                self._send_notification(
                    profile,
                    session,
                    AutoMessage.EventType.PAYMENT_CONFIRMED,
                    {
                        'amount': payment_data.get('amount', session.cart_total),
                        'order_number': payment_data.get('order_number', ''),
                    }
                )

        elif event_type == 'payment_failed':
            if profile.payment_confirmation_enabled:
                self._send_notification(
                    profile,
                    session,
                    AutoMessage.EventType.PAYMENT_FAILED,
                    payment_data
                )

        self._log_action(
            profile,
            AutomationLog.ActionType.WEBHOOK_RECEIVED,
            f"Payment event: {event_type}",
            phone_number=session.phone_number,
            session=session,
            event_type=event_type,
            request_data=payment_data
        )

        return True

    def handle_order_event(
        self,
        api_key: str,
        session_id: str,
        event_type: str,
        order_data: Dict
    ) -> bool:
        """Handle order events from external site."""
        profile = self._validate_api_key(api_key)
        if not profile:
            return False

        session = self.get_session_by_id(session_id)
        if not session:
            logger.warning(f"Order event for unknown session: {session_id}")
            return False

        session.external_order_id = order_data.get('order_id', '')
        
        event_mapping = {
            'order_confirmed': AutoMessage.EventType.ORDER_CONFIRMED,
            'order_preparing': AutoMessage.EventType.ORDER_PREPARING,
            'order_ready': AutoMessage.EventType.ORDER_READY,
            'order_shipped': AutoMessage.EventType.ORDER_SHIPPED,
            'order_out_for_delivery': AutoMessage.EventType.ORDER_OUT_FOR_DELIVERY,
            'order_delivered': AutoMessage.EventType.ORDER_DELIVERED,
            'order_cancelled': AutoMessage.EventType.ORDER_CANCELLED,
        }

        if event_type == 'order_placed':
            session.status = CustomerSession.SessionStatus.ORDER_PLACED
        elif event_type == 'order_delivered':
            session.status = CustomerSession.SessionStatus.COMPLETED

        session.save()

        # Send notification
        if profile.order_status_notification_enabled and event_type in event_mapping:
            self._send_notification(
                profile,
                session,
                event_mapping[event_type],
                {
                    'order_number': order_data.get('order_number', ''),
                    'tracking_code': order_data.get('tracking_code', ''),
                    'delivery_estimate': order_data.get('delivery_estimate', ''),
                    **order_data
                }
            )

        self._log_action(
            profile,
            AutomationLog.ActionType.WEBHOOK_RECEIVED,
            f"Order event: {event_type}",
            phone_number=session.phone_number,
            session=session,
            event_type=event_type,
            request_data=order_data
        )

        return True

    # ==================== Notifications ====================

    def _send_notification(
        self,
        profile: CompanyProfile,
        session: CustomerSession,
        event_type: str,
        context: Dict
    ) -> bool:
        """Send a notification to the customer."""
        # Check if already sent
        if session.was_notification_sent(event_type):
            logger.info(f"Notification {event_type} already sent to {session.phone_number}")
            return False

        message = self._send_auto_message(profile, session, event_type, context)
        if message:
            session.add_notification(event_type)
            return True
        return False

    def _send_auto_message(
        self,
        profile: CompanyProfile,
        session: CustomerSession,
        event_type: str,
        extra_context: Dict = None
    ) -> Optional[str]:
        """Send an auto message for a specific event."""
        auto_message = AutoMessage.objects.filter(
            company=profile,
            event_type=event_type,
            is_active=True
        ).order_by('priority').first()

        if not auto_message:
            return None

        # Build context
        context = {
            'customer_name': session.customer_name or 'Cliente',
            'phone_number': session.phone_number,
            'cart_total': f"{session.cart_total:.2f}",
            'company_name': profile.company_name,
            'website_url': profile.website_url,
            'menu_url': profile.menu_url,
            **(extra_context or {})
        }

        # Render message
        message_text = auto_message.render_message(context)

        # Send via WhatsApp
        try:
            if auto_message.buttons:
                self.whatsapp_service.send_interactive_buttons(
                    account_id=str(profile.account_id),
                    to=session.phone_number,
                    body_text=message_text,
                    buttons=auto_message.buttons
                )
            else:
                self.whatsapp_service.send_text_message(
                    account_id=str(profile.account_id),
                    to=session.phone_number,
                    text=message_text
                )

            self._log_action(
                profile,
                AutomationLog.ActionType.MESSAGE_SENT,
                f"Auto message sent: {event_type}",
                phone_number=session.phone_number,
                session=session,
                event_type=event_type,
                response_data={'message': message_text}
            )

            return message_text

        except Exception as e:
            logger.error(f"Failed to send auto message: {str(e)}")
            self._log_action(
                profile,
                AutomationLog.ActionType.ERROR,
                f"Failed to send auto message: {event_type}",
                phone_number=session.phone_number,
                session=session,
                is_error=True,
                error_message=str(e)
            )
            return None

    def _schedule_abandoned_cart_notification(
        self,
        profile: CompanyProfile,
        session: CustomerSession
    ):
        """Schedule abandoned cart notification."""
        from ..tasks import send_abandoned_cart_notification
        
        delay_seconds = profile.abandoned_cart_delay_minutes * 60
        send_abandoned_cart_notification.apply_async(
            args=[str(session.id)],
            countdown=delay_seconds
        )

    # ==================== Helpers ====================

    def _validate_api_key(self, api_key: str) -> Optional[CompanyProfile]:
        """Validate API key and return company profile."""
        try:
            return CompanyProfile.objects.get(
                external_api_key=api_key,
                is_active=True
            )
        except CompanyProfile.DoesNotExist:
            logger.warning(f"Invalid API key: {api_key[:10]}...")
            return None

    def _log_action(
        self,
        profile: CompanyProfile,
        action_type: str,
        description: str,
        phone_number: str = '',
        session: CustomerSession = None,
        event_type: str = '',
        request_data: Dict = None,
        response_data: Dict = None,
        is_error: bool = False,
        error_message: str = ''
    ):
        """Log an automation action."""
        AutomationLog.objects.create(
            company=profile,
            session=session,
            action_type=action_type,
            description=description,
            phone_number=phone_number,
            event_type=event_type,
            request_data=request_data or {},
            response_data=response_data or {},
            is_error=is_error,
            error_message=error_message
        )
