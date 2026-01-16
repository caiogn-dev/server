"""
Email Marketing Service using Resend API.
"""
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from django.utils import timezone
from django.db.models import Count, Sum, Q

logger = logging.getLogger(__name__)

try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    logger.warning("Resend package not installed.")


class EmailMarketingService:
    """Service for email marketing operations."""
    
    def __init__(self):
        self.api_key = os.getenv('RESEND_API_KEY')
        self.default_from_email = os.getenv('RESEND_FROM_EMAIL', 'contato@pastita.com.br')
        self.default_from_name = os.getenv('RESEND_FROM_NAME', 'Pastita')
        
        if RESEND_AVAILABLE and self.api_key:
            resend.api_key = self.api_key
            self.enabled = True
        else:
            self.enabled = False
    
    def get_stats(self, store_id: str) -> Dict[str, Any]:
        """Get marketing statistics for a store."""
        from apps.marketing.models import EmailCampaign, Subscriber
        
        # Campaign stats
        campaigns = EmailCampaign.objects.filter(store_id=store_id)
        total_campaigns = campaigns.count()
        active_campaigns = campaigns.filter(status__in=['scheduled', 'sending']).count()
        
        # Aggregate email stats
        email_stats = campaigns.aggregate(
            total_sent=Sum('emails_sent'),
            total_delivered=Sum('emails_delivered'),
            total_opened=Sum('emails_opened'),
            total_clicked=Sum('emails_clicked'),
        )
        
        # Subscriber stats
        subscribers = Subscriber.objects.filter(store_id=store_id)
        total_subscribers = subscribers.count()
        active_subscribers = subscribers.filter(status='active').count()
        
        # Recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        recent_campaigns = campaigns.filter(created_at__gte=thirty_days_ago).count()
        new_subscribers = subscribers.filter(created_at__gte=thirty_days_ago).count()
        
        return {
            'campaigns': {
                'total': total_campaigns,
                'active': active_campaigns,
                'recent': recent_campaigns,
            },
            'emails': {
                'sent': email_stats['total_sent'] or 0,
                'delivered': email_stats['total_delivered'] or 0,
                'opened': email_stats['total_opened'] or 0,
                'clicked': email_stats['total_clicked'] or 0,
            },
            'subscribers': {
                'total': total_subscribers,
                'active': active_subscribers,
                'new_last_30_days': new_subscribers,
            },
            'rates': {
                'open_rate': self._calculate_rate(
                    email_stats['total_opened'] or 0,
                    email_stats['total_delivered'] or 0
                ),
                'click_rate': self._calculate_rate(
                    email_stats['total_clicked'] or 0,
                    email_stats['total_opened'] or 0
                ),
            }
        }
    
    def _calculate_rate(self, numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0
        return round((numerator / denominator) * 100, 2)
    
    def send_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Send an email campaign."""
        from apps.marketing.models import EmailCampaign, EmailRecipient, Subscriber
        from apps.stores.models import StoreOrder
        
        if not self.enabled:
            return {'success': False, 'error': 'Email service not configured'}
        
        try:
            campaign = EmailCampaign.objects.get(id=campaign_id)
        except EmailCampaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        
        logger.info(f"Sending campaign {campaign_id}: store={campaign.store_id}, audience={campaign.audience_type}, status={campaign.status}")
        
        if campaign.status not in ['draft', 'scheduled']:
            return {'success': False, 'error': f'Campaign cannot be sent (status: {campaign.status})'}
        
        if not campaign.store_id:
            return {'success': False, 'error': 'Campaign has no store associated'}
        
        # Update status
        campaign.status = 'sending'
        campaign.started_at = timezone.now()
        campaign.save()
        
        # Get recipients
        recipients_list = []
        
        if campaign.audience_type == 'all':
            # First get subscribers
            subscribers = Subscriber.objects.filter(
                store=campaign.store,
                status='active',
                accepts_marketing=True
            )
            for sub in subscribers:
                recipients_list.append({
                    'email': sub.email,
                    'name': sub.name or '',
                })
            
            # Also get customers from orders (unique emails)
            orders = StoreOrder.objects.filter(
                store=campaign.store,
                customer_email__isnull=False
            ).exclude(customer_email='').values('customer_email', 'customer_name').distinct()
            
            existing_emails = {r['email'].lower() for r in recipients_list}
            for order in orders:
                email = order['customer_email'].lower()
                if email not in existing_emails:
                    recipients_list.append({
                        'email': order['customer_email'],
                        'name': order['customer_name'] or '',
                    })
                    existing_emails.add(email)
                    
        elif campaign.audience_type == 'customers':
            # Only customers who made orders
            orders = StoreOrder.objects.filter(
                store=campaign.store,
                customer_email__isnull=False
            ).exclude(customer_email='').values('customer_email', 'customer_name').distinct()
            
            seen_emails = set()
            for order in orders:
                email = order['customer_email'].lower()
                if email not in seen_emails:
                    recipients_list.append({
                        'email': order['customer_email'],
                        'name': order['customer_name'] or '',
                    })
                    seen_emails.add(email)
                    
        elif campaign.audience_type == 'subscribers':
            # Only subscribers
            subscribers = Subscriber.objects.filter(
                store=campaign.store,
                status='active',
                accepts_marketing=True
            )
            for sub in subscribers:
                recipients_list.append({
                    'email': sub.email,
                    'name': sub.name or '',
                })
                    
        elif campaign.audience_type == 'custom':
            for recipient in (campaign.recipient_list or []):
                if recipient.get('email'):
                    recipients_list.append({
                        'email': recipient.get('email'),
                        'name': recipient.get('name', ''),
                    })
        else:
            # Segment filtering from subscribers
            subscribers = Subscriber.objects.filter(
                store=campaign.store,
                status='active',
                accepts_marketing=True
            )
            # Apply filters from audience_filters
            filters = campaign.audience_filters or {}
            if filters.get('tags'):
                subscribers = subscribers.filter(tags__contains=filters['tags'])
            if filters.get('min_orders'):
                subscribers = subscribers.filter(total_orders__gte=filters['min_orders'])
            
            for sub in subscribers:
                recipients_list.append({
                    'email': sub.email,
                    'name': sub.name or '',
                })
        
        # Use recipients_list instead of subscribers
        subscribers = recipients_list
        
        logger.info(f"Campaign {campaign.id}: Found {len(subscribers)} recipients (audience_type: {campaign.audience_type})")
        
        if not subscribers:
            campaign.status = 'sent'
            campaign.completed_at = timezone.now()
            campaign.emails_sent = 0
            campaign.total_recipients = 0
            campaign.save()
            return {
                'success': True,
                'sent': 0,
                'failed': 0,
                'campaign_id': str(campaign.id),
                'message': 'No recipients found for this campaign'
            }
        
        # Create recipients and send
        sent_count = 0
        failed_count = 0
        
        from_email = campaign.from_email or self.default_from_email
        from_name = campaign.from_name or self.default_from_name
        
        # Get store name for personalization
        store_name = campaign.store.name if campaign.store else 'Loja'
        
        for subscriber in subscribers:
            if isinstance(subscriber, dict):
                email = subscriber['email']
                name = subscriber.get('name', '')
                first_name = name.split()[0] if name else ''
            else:
                email = subscriber.email
                name = subscriber.name or ''
                first_name = name.split()[0] if name else ''
            
            # Create recipient record
            recipient, created = EmailRecipient.objects.get_or_create(
                campaign=campaign,
                email=email,
                defaults={'name': name}
            )
            
            if recipient.status != 'pending':
                continue
            
            # Get store URL
            store_url = ''
            store_domain = ''
            if campaign.store:
                store_domain = campaign.store.domain or ''
                if store_domain:
                    store_url = f'https://{store_domain}'
                else:
                    store_url = f'https://pastita.com.br'  # fallback
            
            # Personalize content with multiple variables
            personalization_vars = {
                'name': name,
                'customer_name': name,
                'first_name': first_name,
                'email': email,
                'store_name': store_name,
                'year': str(timezone.now().year),
                'store_url': store_url,
                'store_domain': store_domain,
                # Common discount placeholders - get from campaign metadata if available
                'discount_value': str(campaign.audience_filters.get('discount_value', '10')) if campaign.audience_filters else '10',
                'discount_code': campaign.audience_filters.get('discount_code', 'DESCONTO10') if campaign.audience_filters else 'DESCONTO10',
                'coupon_code': campaign.audience_filters.get('coupon_code', '') if campaign.audience_filters else '',
            }
            html_content = self._personalize_content(
                campaign.html_content,
                personalization_vars
            )
            
            # Also personalize subject
            personalized_subject = self._personalize_content(
                campaign.subject,
                personalization_vars
            )
            
            # Send via Resend
            try:
                response = resend.Emails.send({
                    'from': f'{from_name} <{from_email}>',
                    'to': [email],
                    'subject': personalized_subject,
                    'html': html_content,
                })
                
                recipient.status = 'sent'
                recipient.resend_id = response.get('id', '')
                recipient.sent_at = timezone.now()
                sent_count += 1
                
            except Exception as e:
                recipient.status = 'failed'
                recipient.error_message = str(e)
                failed_count += 1
                logger.error(f"Failed to send email to {email}: {e}")
            
            recipient.save()
        
        # Update campaign stats
        campaign.emails_sent = sent_count
        campaign.total_recipients = sent_count + failed_count
        
        if failed_count == 0:
            campaign.status = 'sent'
            campaign.completed_at = timezone.now()
        else:
            campaign.status = 'sent'  # Still mark as sent even with some failures
            campaign.completed_at = timezone.now()
        
        campaign.save()
        
        return {
            'success': True,
            'sent': sent_count,
            'failed': failed_count,
            'campaign_id': str(campaign.id)
        }
    
    def _personalize_content(self, content: str, variables: Dict[str, str]) -> str:
        """Replace variables in content."""
        import re
        
        for key, value in variables.items():
            val = str(value) if value else ''
            # Handle different formats: {{key}}, {{ key }}, {key}
            content = content.replace(f'{{{{{key}}}}}', val)  # {{key}}
            content = content.replace(f'{{{{ {key} }}}}', val)  # {{ key }}
            content = content.replace(f'{{{key}}}', val)  # {key}
        
        # Also handle any remaining {{variable}} patterns with regex
        # Replace any unmatched {{...}} with empty string
        content = re.sub(r'\{\{\s*\w+\s*\}\}', '', content)
        
        return content
    
    def send_single_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a single email."""
        if not self.enabled:
            logger.warning(f"Email not sent (disabled): {subject} to {to_email}")
            return {'success': False, 'error': 'Email service not configured'}
        
        try:
            params = {
                'from': f'{from_name or self.default_from_name} <{from_email or self.default_from_email}>',
                'to': [to_email],
                'subject': subject,
                'html': html_content,
            }
            
            if reply_to:
                params['reply_to'] = reply_to
            
            response = resend.Emails.send(params)
            logger.info(f"Email sent: {subject} to {to_email}")
            
            return {
                'success': True,
                'id': response.get('id'),
            }
        
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_coupon_email(
        self,
        store_id: str,
        to_email: str,
        customer_name: str,
        coupon_code: str,
        discount_value: str,
        expiry_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a coupon email."""
        from apps.stores.models import Store
        
        try:
            store = Store.objects.get(id=store_id)
        except Store.DoesNotExist:
            return {'success': False, 'error': 'Store not found'}
        
        expiry_text = f"Válido até {expiry_date}" if expiry_date else "Por tempo limitado"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <tr>
                    <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A44 100%); padding: 40px 20px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px;">🎁 Presente Especial!</h1>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 40px 30px;">
                        <p style="font-size: 18px; color: #333; margin: 0 0 20px;">
                            Olá, <strong>{customer_name}</strong>!
                        </p>
                        <p style="font-size: 16px; color: #666; line-height: 1.6; margin: 0 0 30px;">
                            Preparamos um cupom exclusivo para você aproveitar nossas deliciosas massas artesanais.
                        </p>
                        
                        <div style="background: linear-gradient(135deg, #C9A050 0%, #D4AF61 100%); border-radius: 12px; padding: 30px; text-align: center; margin: 0 0 30px;">
                            <p style="color: #722F37; font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: 2px;">
                                Seu cupom de desconto
                            </p>
                            <p style="color: #722F37; font-size: 36px; font-weight: bold; margin: 0 0 10px; letter-spacing: 4px;">
                                {coupon_code}
                            </p>
                            <p style="color: #722F37; font-size: 24px; font-weight: bold; margin: 0;">
                                {discount_value} OFF
                            </p>
                        </div>
                        
                        <p style="font-size: 14px; color: #999; text-align: center; margin: 0 0 30px;">
                            {expiry_text}
                        </p>
                        
                        <div style="text-align: center;">
                            <a href="https://pastita.com.br/cardapio" 
                               style="display: inline-block; background-color: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                                Usar Cupom Agora →
                            </a>
                        </div>
                    </td>
                </tr>
                <tr>
                    <td style="background-color: #f9f9f9; padding: 30px; text-align: center;">
                        <p style="color: #999; font-size: 12px; margin: 0;">
                            {store.name}<br>
                            Massas Artesanais
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return self.send_single_email(
            to_email=to_email,
            subject=f"🎁 {discount_value} de desconto esperando por você!",
            html_content=html,
        )
    
    def send_welcome_email(
        self,
        store_id: str,
        to_email: str,
        customer_name: str,
    ) -> Dict[str, Any]:
        """Send a welcome email to new subscriber."""
        from apps.stores.models import Store
        
        try:
            store = Store.objects.get(id=store_id)
        except Store.DoesNotExist:
            return {'success': False, 'error': 'Store not found'}
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <tr>
                    <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A44 100%); padding: 40px 20px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px;">🍝 Bem-vindo à {store.name}!</h1>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 40px 30px;">
                        <p style="font-size: 18px; color: #333; margin: 0 0 20px;">
                            Olá, <strong>{customer_name}</strong>!
                        </p>
                        <p style="font-size: 16px; color: #666; line-height: 1.6; margin: 0 0 20px;">
                            Estamos muito felizes em ter você conosco! 🎉
                        </p>
                        <p style="font-size: 16px; color: #666; line-height: 1.6; margin: 0 0 30px;">
                            A partir de agora você receberá novidades, promoções exclusivas e muito mais diretamente no seu email.
                        </p>
                        
                        <div style="background-color: #f9f9f9; border-radius: 12px; padding: 25px; margin: 0 0 30px;">
                            <h3 style="color: #722F37; margin: 0 0 15px; font-size: 18px;">O que você pode esperar:</h3>
                            <ul style="color: #666; font-size: 14px; line-height: 1.8; margin: 0; padding-left: 20px;">
                                <li>Cupons exclusivos de desconto</li>
                                <li>Novidades do cardápio</li>
                                <li>Promoções especiais</li>
                                <li>Dicas e receitas</li>
                            </ul>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="https://pastita.com.br/cardapio" 
                               style="display: inline-block; background-color: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                                Conhecer o Cardápio →
                            </a>
                        </div>
                    </td>
                </tr>
                <tr>
                    <td style="background-color: #f9f9f9; padding: 30px; text-align: center;">
                        <p style="color: #999; font-size: 12px; margin: 0;">
                            {store.name}<br>
                            Massas Artesanais
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return self.send_single_email(
            to_email=to_email,
            subject=f"🍝 Bem-vindo à {store.name}!",
            html_content=html,
        )


# Singleton instance
email_marketing_service = EmailMarketingService()
