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

from .marca_da_loja import contatos_reais, marca_da_loja, moldura

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

        whatsapp_stats = self._get_whatsapp_stats(store_id)

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
            },
            'whatsapp': whatsapp_stats,
        }

    def _get_whatsapp_stats(self, store_id: str) -> Dict[str, Any]:
        """Agrega métricas das campanhas de WhatsApp da loja.

        As campanhas (apps.campaigns.Campaign) são escopadas por WhatsAppAccount,
        que não tem FK direta pra Store — o vínculo é via StoreIntegration
        (phone_number_id / waba_id). Antes o painel de Marketing zerava o card de
        WhatsApp (total_sent/read_rate hardcoded em 0 no front) por falta deste bloco.
        """
        try:
            from apps.campaigns.models import Campaign
            from apps.whatsapp.models.account import WhatsAppAccount
            from apps.stores.models import StoreIntegration
        except ImportError:
            return self._empty_whatsapp_stats()

        integrations = StoreIntegration.objects.filter(store_id=store_id)
        phone_ids = [p for p in integrations.values_list('phone_number_id', flat=True) if p]
        waba_ids = [w for w in integrations.values_list('waba_id', flat=True) if w]
        if not phone_ids and not waba_ids:
            return self._empty_whatsapp_stats()

        account_filter = Q()
        if phone_ids:
            account_filter |= Q(phone_number_id__in=phone_ids)
        if waba_ids:
            account_filter |= Q(waba_id__in=waba_ids)
        account_ids = list(
            WhatsAppAccount.objects.filter(account_filter).values_list('id', flat=True)
        )
        if not account_ids:
            return self._empty_whatsapp_stats()

        campaigns = Campaign.objects.filter(account_id__in=account_ids)
        agg = campaigns.aggregate(
            total_sent=Sum('messages_sent'),
            total_delivered=Sum('messages_delivered'),
            total_read=Sum('messages_read'),
        )
        total_sent = agg['total_sent'] or 0
        total_delivered = agg['total_delivered'] or 0
        total_read = agg['total_read'] or 0
        return {
            'total_campaigns': campaigns.count(),
            'total_sent': total_sent,
            'total_delivered': total_delivered,
            'total_read': total_read,
            'delivery_rate': self._calculate_rate(total_delivered, total_sent),
            'read_rate': self._calculate_rate(total_read, total_delivered),
        }

    def _empty_whatsapp_stats(self) -> Dict[str, Any]:
        return {
            'total_campaigns': 0,
            'total_sent': 0,
            'total_delivered': 0,
            'total_read': 0,
            'delivery_rate': 0,
            'read_rate': 0,
        }

    def _calculate_rate(self, numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0
        return round((numerator / denominator) * 100, 2)
    
    def send_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Send an email campaign."""
        from apps.marketing.models import EmailCampaign, EmailRecipient, Subscriber
        from apps.stores.models import StoreOrder
        
        logger.info(f"[send_campaign] Starting campaign {campaign_id}")
        
        if not self.enabled:
            logger.warning(f"[send_campaign] Email service not enabled. API Key: {'set' if self.api_key else 'not set'}, Resend: {RESEND_AVAILABLE}")
            return {'success': False, 'error': 'Email service not configured. Please configure RESEND_API_KEY.'}
        
        try:
            campaign = EmailCampaign.objects.get(id=campaign_id)
            logger.info(f"[send_campaign] Found campaign: {campaign.name}, store={campaign.store_id}, status={campaign.status}")
        except EmailCampaign.DoesNotExist:
            logger.error(f"[send_campaign] Campaign {campaign_id} not found")
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
        
        # A identidade é da LOJA. Em 10/ago uma campanha da Cê Saladas saiu
        # assinada "Pastita <contato@pastita.com.br>" para 39 pessoas, com o
        # botão apontando para pastita.com.br — o nome, as cores e a tagline da
        # loja estavam no banco e eram ignorados.
        marca = marca_da_loja(getattr(campaign, 'store', None))
        from_email = campaign.from_email or marca['from_email']
        from_name = campaign.from_name or marca['from_name']
        store_name = marca['nome']
        
        # Endereço inventado pelo próprio sistema (@whatsapp.bot,
        # @local.invalid) não é caixa de e-mail: 15 dos 39 destinatários da
        # campanha de 10/ago eram assim. Cada bounce corrói a reputação do
        # domínio no Resend e prejudica a entrega de quem tem e-mail real.
        emails_brutos = [
            s_['email'] if isinstance(s_, dict) else s_.email for s_ in subscribers
        ]
        descartados = len(emails_brutos) - len(contatos_reais(emails_brutos))
        if descartados:
            logger.info(
                '[campanha] %s destinatários descartados por serem endereços '
                'internos (WhatsApp/balcão)', descartados,
            )

        for subscriber in subscribers:
            email_bruto = subscriber['email'] if isinstance(subscriber, dict) else subscriber.email
            if not contatos_reais([email_bruto]):
                continue
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
            
            # A URL vem do SSOT do storefront, não de uma constante: a
            # variável {store_url} do template levava todo cliente, de toda
            # loja, para pastita.com.br.
            store_url = marca['url']
            store_domain = store_url.replace('https://', '').replace('http://', '')
            
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

        marca = marca_da_loja(store)
        corpo = f"""
            <p style="font-size:18px;color:#333;margin:0 0 20px;">
                Olá, <strong>{customer_name}</strong>!
            </p>
            <p style="font-size:16px;color:#666;line-height:1.6;margin:0 0 30px;">
                Preparamos um cupom exclusivo para você usar na {marca['nome']}.
            </p>
            <div style="background:{marca['cor_secundaria']};border-radius:12px;padding:30px;text-align:center;margin:0 0 30px;">
                <p style="color:#ffffff;font-size:14px;margin:0 0 10px;text-transform:uppercase;letter-spacing:2px;">
                    Seu cupom de desconto
                </p>
                <p style="color:#ffffff;font-size:36px;font-weight:bold;margin:0 0 10px;letter-spacing:4px;">
                    {coupon_code}
                </p>
                <p style="color:#ffffff;font-size:24px;font-weight:bold;margin:0;">
                    {discount_value} OFF
                </p>
            </div>
            <p style="font-size:14px;color:#999;text-align:center;margin:0;">{expiry_text}</p>
        """
        html = moldura(
            marca,
            titulo='🎁 Presente especial!',
            corpo=corpo,
            cta_texto='Usar cupom agora',
            cta_url=marca['url'],
        )

        return self.send_single_email(
            to_email=to_email,
            subject=f"🎁 {discount_value} de desconto na {marca['nome']}!",
            html_content=html,
            from_name=marca['from_name'],
            from_email=marca['from_email'],
            reply_to=marca['reply_to'] or None,
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
        
        marca = marca_da_loja(store)
        corpo = f"""
            <p style="font-size:18px;color:#333;margin:0 0 20px;">
                Olá, <strong>{customer_name}</strong>!
            </p>
            <p style="font-size:16px;color:#666;line-height:1.6;margin:0 0 20px;">
                Estamos muito felizes em ter você com a gente! 🎉
            </p>
            <p style="font-size:16px;color:#666;line-height:1.6;margin:0 0 30px;">
                A partir de agora você recebe novidades e promoções exclusivas da
                {marca['nome']} direto no seu e-mail.
            </p>
            <div style="background-color:#f9f9f9;border-radius:12px;padding:25px;margin:0;">
                <h3 style="color:{marca['cor_primaria']};margin:0 0 15px;font-size:18px;">O que você pode esperar:</h3>
                <ul style="color:#666;font-size:14px;line-height:1.8;margin:0;padding-left:20px;">
                    <li>Cupons exclusivos de desconto</li>
                    <li>Novidades do cardápio</li>
                    <li>Promoções especiais</li>
                </ul>
            </div>
        """
        html = moldura(
            marca,
            titulo=f"Bem-vindo à {marca['nome']}!",
            corpo=corpo,
            cta_texto='Conhecer o cardápio',
            cta_url=marca['url'],
        )

        return self.send_single_email(
            to_email=to_email,
            subject=f"Bem-vindo à {marca['nome']}!",
            html_content=html,
            from_name=marca['from_name'],
            from_email=marca['from_email'],
            reply_to=marca['reply_to'] or None,
        )


# Singleton instance
email_marketing_service = EmailMarketingService()
