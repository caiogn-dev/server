"""
Email Automation Service

Handles automated email sending based on triggers like:
- New user registration
- Order status changes
- Payment events
- Cart abandonment
- etc.
"""
import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class EmailAutomationService:
    """Service for handling automated email triggers."""
    
    def __init__(self):
        from apps.marketing.services import email_marketing_service
        self.email_service = email_marketing_service
    
    def trigger(
        self,
        store_id: str,
        trigger_type: str,
        recipient_email: str,
        recipient_name: str = '',
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Trigger an automated email.
        
        Args:
            store_id: The store ID
            trigger_type: Type of trigger (e.g., 'order_confirmed', 'new_user')
            recipient_email: Email address to send to
            recipient_name: Name of recipient
            context: Additional context for personalization
        
        Returns:
            Dict with success status and details
        """
        from apps.marketing.models import EmailAutomation, EmailAutomationLog
        
        if not recipient_email:
            return {'success': False, 'error': 'No recipient email provided'}
        
        # Find active automation for this trigger
        automation = EmailAutomation.objects.filter(
            store_id=store_id,
            trigger_type=trigger_type,
            is_active=True
        ).first()
        
        if not automation:
            logger.debug(f"No active automation for {trigger_type} in store {store_id}")
            return {'success': False, 'error': 'No automation configured for this trigger'}
        
        # Check conditions
        if automation.conditions:
            if not self._check_conditions(automation.conditions, context or {}):
                return {'success': False, 'error': 'Conditions not met'}
        
        # Create log entry
        log = EmailAutomationLog.objects.create(
            automation=automation,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            trigger_data=context or {},
            status='pending'
        )
        
        # If there's a delay, schedule for later
        if automation.delay_minutes > 0:
            log.scheduled_at = timezone.now() + timezone.timedelta(minutes=automation.delay_minutes)
            log.save()
            return {
                'success': True,
                'scheduled': True,
                'scheduled_at': log.scheduled_at.isoformat(),
                'log_id': str(log.id)
            }
        
        # Send immediately
        return self._send_automation_email(automation, log, context or {})
    
    def _send_automation_email(
        self,
        automation,
        log,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send the automated email."""
        from apps.marketing.models import EmailAutomationLog
        
        try:
            # Get content from template or automation
            if automation.template:
                subject = automation.template.subject
                html_content = automation.template.html_content
            else:
                subject = automation.subject
                html_content = automation.html_content
            
            # Build personalization context
            store_name = automation.store.name if automation.store else 'Loja'
            first_name = log.recipient_name.split()[0] if log.recipient_name else ''
            
            personalization = {
                'name': log.recipient_name,
                'customer_name': log.recipient_name,
                'first_name': first_name,
                'email': log.recipient_email,
                'store_name': store_name,
                'year': str(timezone.now().year),
                **context
            }
            
            # Personalize content
            for key, value in personalization.items():
                subject = subject.replace(f'{{{{{key}}}}}', str(value or ''))
                html_content = html_content.replace(f'{{{{{key}}}}}', str(value or ''))
            
            # Send via email service
            result = self.email_service.send_single_email(
                to_email=log.recipient_email,
                subject=subject,
                html_content=html_content,
                from_name=store_name
            )
            
            if result.get('success'):
                log.status = 'sent'
                log.sent_at = timezone.now()
                log.resend_id = result.get('id', '')
                log.save()
                
                # Update automation stats
                automation.total_sent += 1
                automation.save(update_fields=['total_sent'])
                
                logger.info(f"Automation email sent: {automation.trigger_type} to {log.recipient_email}")
                return {'success': True, 'log_id': str(log.id)}
            else:
                log.status = 'failed'
                log.error_message = result.get('error', 'Unknown error')
                log.save()
                return {'success': False, 'error': result.get('error')}
                
        except Exception as e:
            logger.error(f"Failed to send automation email: {e}")
            log.status = 'failed'
            log.error_message = str(e)
            log.save()
            return {'success': False, 'error': str(e)}
    
    def _check_conditions(self, conditions: Dict, context: Dict) -> bool:
        """Check if conditions are met for sending."""
        # Example conditions:
        # {"min_order_value": 100, "customer_has_orders": true}
        
        if 'min_order_value' in conditions:
            order_value = context.get('order_total', 0)
            if order_value < conditions['min_order_value']:
                return False
        
        if 'customer_has_orders' in conditions:
            has_orders = context.get('customer_has_orders', False)
            if conditions['customer_has_orders'] != has_orders:
                return False
        
        return True
    
    def process_scheduled(self) -> Dict[str, Any]:
        """Process scheduled automation emails (called by celery task)."""
        from apps.marketing.models import EmailAutomationLog
        
        now = timezone.now()
        pending_logs = EmailAutomationLog.objects.filter(
            status='pending',
            scheduled_at__lte=now
        ).select_related('automation', 'automation__store', 'automation__template')
        
        sent = 0
        failed = 0
        
        for log in pending_logs:
            result = self._send_automation_email(
                log.automation,
                log,
                log.trigger_data
            )
            if result.get('success'):
                sent += 1
            else:
                failed += 1
        
        return {'sent': sent, 'failed': failed}
    
    # ==========================================================================
    # CONVENIENCE METHODS FOR COMMON TRIGGERS
    # ==========================================================================
    
    def on_new_user(
        self,
        store_id: str,
        email: str,
        name: str = '',
        **extra_context
    ) -> Dict[str, Any]:
        """Trigger email for new user registration."""
        return self.trigger(
            store_id=store_id,
            trigger_type='new_user',
            recipient_email=email,
            recipient_name=name,
            context=extra_context
        )
    
    def on_order_received(
        self,
        store_id: str,
        email: str,
        name: str = '',
        order_number: str = '',
        order_total: float = 0,
        payment_method: str = '',
        **extra_context
    ) -> Dict[str, Any]:
        """
        Trigger email when order is RECEIVED (created, awaiting payment).
        This is sent BEFORE payment confirmation.
        """
        return self.trigger(
            store_id=store_id,
            trigger_type='order_received',
            recipient_email=email,
            recipient_name=name,
            context={
                'order_number': order_number,
                'order_total': f'{order_total:.2f}',
                'payment_method': payment_method,
                'status_message': 'Aguardando pagamento',
                **extra_context
            }
        )
    
    def on_order_confirmed(
        self,
        store_id: str,
        email: str,
        name: str = '',
        order_number: str = '',
        order_total: float = 0,
        **extra_context
    ) -> Dict[str, Any]:
        """
        Trigger email for order confirmation (AFTER payment confirmed).
        This should only be called after webhook confirms payment.
        """
        return self.trigger(
            store_id=store_id,
            trigger_type='order_confirmed',
            recipient_email=email,
            recipient_name=name,
            context={
                'order_number': order_number,
                'order_total': f'{order_total:.2f}',
                'status_message': 'Pagamento confirmado! Pedido em produção.',
                **extra_context
            }
        )
    
    def on_order_shipped(
        self,
        store_id: str,
        email: str,
        name: str = '',
        order_number: str = '',
        tracking_code: str = '',
        **extra_context
    ) -> Dict[str, Any]:
        """Trigger email for order shipped."""
        return self.trigger(
            store_id=store_id,
            trigger_type='order_shipped',
            recipient_email=email,
            recipient_name=name,
            context={
                'order_number': order_number,
                'tracking_code': tracking_code,
                **extra_context
            }
        )
    
    def on_order_delivered(
        self,
        store_id: str,
        email: str,
        name: str = '',
        order_number: str = '',
        **extra_context
    ) -> Dict[str, Any]:
        """Trigger email for order delivered."""
        return self.trigger(
            store_id=store_id,
            trigger_type='order_delivered',
            recipient_email=email,
            recipient_name=name,
            context={
                'order_number': order_number,
                **extra_context
            }
        )
    
    def on_payment_confirmed(
        self,
        store_id: str,
        email: str,
        name: str = '',
        order_number: str = '',
        amount: float = 0,
        **extra_context
    ) -> Dict[str, Any]:
        """Trigger email for payment confirmation."""
        return self.trigger(
            store_id=store_id,
            trigger_type='payment_confirmed',
            recipient_email=email,
            recipient_name=name,
            context={
                'order_number': order_number,
                'amount': f'{amount:.2f}',
                **extra_context
            }
        )
    
    def on_cart_abandoned(
        self,
        store_id: str,
        email: str,
        name: str = '',
        cart_total: float = 0,
        cart_items: list = None,
        **extra_context
    ) -> Dict[str, Any]:
        """Trigger email for abandoned cart."""
        return self.trigger(
            store_id=store_id,
            trigger_type='cart_abandoned',
            recipient_email=email,
            recipient_name=name,
            context={
                'cart_total': f'{cart_total:.2f}',
                'cart_items': cart_items or [],
                **extra_context
            }
        )


# Singleton instance
email_automation_service = EmailAutomationService()
