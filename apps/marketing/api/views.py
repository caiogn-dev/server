"""
Marketing API views.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from apps.marketing.models import (
    EmailTemplate, EmailCampaign, EmailRecipient, Subscriber,
    EmailAutomation, EmailAutomationLog
)
from apps.marketing.services import email_marketing_service
from apps.marketing.services.email_automation_service import email_automation_service
from .serializers import (
    EmailTemplateSerializer, EmailTemplateListSerializer,
    EmailCampaignSerializer, EmailCampaignListSerializer,
    EmailRecipientSerializer, SubscriberSerializer, SubscriberListSerializer,
    MarketingStatsSerializer, SendCouponEmailSerializer, SendWelcomeEmailSerializer,
    EmailAutomationSerializer, EmailAutomationListSerializer,
    EmailAutomationLogSerializer, TriggerAutomationSerializer,
)


class EmailTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for email templates."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = EmailTemplateSerializer
    
    def get_queryset(self):
        queryset = EmailTemplate.objects.all()
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailTemplateListSerializer
        return EmailTemplateSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def presets(self, request):
        """Get preset templates."""
        presets = [
            {
                'id': 'coupon',
                'name': 'Cupom de Desconto',
                'description': 'Email com cupom de desconto para clientes',
                'template_type': 'coupon',
                'preview_image': '/templates/coupon-preview.png',
            },
            {
                'id': 'welcome',
                'name': 'Boas-vindas',
                'description': 'Email de boas-vindas para novos inscritos',
                'template_type': 'welcome',
                'preview_image': '/templates/welcome-preview.png',
            },
            {
                'id': 'promotion',
                'name': 'Promoção',
                'description': 'Email promocional com ofertas especiais',
                'template_type': 'promotion',
                'preview_image': '/templates/promotion-preview.png',
            },
            {
                'id': 'abandoned_cart',
                'name': 'Carrinho Abandonado',
                'description': 'Lembrete para clientes que abandonaram o carrinho',
                'template_type': 'abandoned_cart',
                'preview_image': '/templates/cart-preview.png',
            },
            {
                'id': 'newsletter',
                'name': 'Newsletter',
                'description': 'Newsletter com novidades e conteúdo',
                'template_type': 'newsletter',
                'preview_image': '/templates/newsletter-preview.png',
            },
        ]
        return Response(presets)


class EmailCampaignViewSet(viewsets.ModelViewSet):
    """ViewSet for email campaigns."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = EmailCampaignSerializer
    
    def get_queryset(self):
        queryset = EmailCampaign.objects.all()
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailCampaignListSerializer
        return EmailCampaignSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send a campaign."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Sending campaign {pk}")
            result = email_marketing_service.send_campaign(pk)
            logger.info(f"Campaign {pk} send result: {result}")
            
            if result['success']:
                return Response(result)
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error sending campaign {pk}: {e}")
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """Schedule a campaign."""
        campaign = self.get_object()
        scheduled_at = request.data.get('scheduled_at')
        
        if not scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        campaign.scheduled_at = scheduled_at
        campaign.status = 'scheduled'
        campaign.save()
        
        return Response(EmailCampaignSerializer(campaign).data)
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a campaign."""
        campaign = self.get_object()
        
        if campaign.status not in ['sending', 'scheduled']:
            return Response(
                {'error': 'Campaign cannot be paused'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        campaign.status = 'paused'
        campaign.save()
        
        return Response(EmailCampaignSerializer(campaign).data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a campaign."""
        campaign = self.get_object()
        
        if campaign.status in ['sent', 'cancelled']:
            return Response(
                {'error': 'Campaign cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        campaign.status = 'cancelled'
        campaign.save()
        
        return Response(EmailCampaignSerializer(campaign).data)
    
    @action(detail=True, methods=['get'])
    def recipients(self, request, pk=None):
        """Get campaign recipients."""
        campaign = self.get_object()
        recipients = EmailRecipient.objects.filter(campaign=campaign)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            recipients = recipients.filter(status=status_filter)
        
        serializer = EmailRecipientSerializer(recipients, many=True)
        return Response(serializer.data)


class SubscriberViewSet(viewsets.ModelViewSet):
    """ViewSet for subscribers."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriberSerializer
    
    def get_queryset(self):
        queryset = Subscriber.objects.all()
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SubscriberListSerializer
        return SubscriberSerializer
    
    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """Import subscribers from CSV."""
        store_id = request.data.get('store')
        contacts = request.data.get('contacts', [])
        
        if not store_id:
            return Response(
                {'error': 'store is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created = 0
        updated = 0
        
        for contact in contacts:
            email = contact.get('email')
            if not email:
                continue
            
            subscriber, was_created = Subscriber.objects.update_or_create(
                store_id=store_id,
                email=email,
                defaults={
                    'name': contact.get('name', ''),
                    'phone': contact.get('phone', ''),
                    'source': 'import',
                }
            )
            
            if was_created:
                created += 1
            else:
                updated += 1
        
        return Response({
            'created': created,
            'updated': updated,
            'total': created + updated,
        })
    
    @action(detail=True, methods=['post'])
    def unsubscribe(self, request, pk=None):
        """Unsubscribe a subscriber."""
        from django.utils import timezone
        
        subscriber = self.get_object()
        subscriber.status = 'unsubscribed'
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save()
        
        return Response(SubscriberSerializer(subscriber).data)


class CustomersViewSet(viewsets.ViewSet):
    """
    ViewSet for unified customer list.
    Aggregates customers from multiple sources:
    - Django Users (registered users)
    - Orders (customers who made purchases)
    - Subscribers (marketing contacts)
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get all customers for a store (aggregated from multiple sources)."""
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store, StoreOrder
        from django.db.models import Count, Sum, Max
        
        User = get_user_model()
        
        store_id = request.query_params.get('store')
        if not store_id:
            return Response(
                {'error': 'store parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get store to find associated WhatsApp account
        try:
            store = Store.objects.get(id=store_id)
        except Store.DoesNotExist:
            return Response({'error': 'Store not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Dictionary to aggregate customers by email
        customers_dict = {}
        
        # 1. Get ALL registered users (they are potential customers)
        # Include all non-staff users who registered via the site
        users = User.objects.filter(
            is_active=True
        ).exclude(
            is_staff=True
        ).exclude(
            is_superuser=True
        ).prefetch_related('profile')
        
        # Debug: log user count
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"CustomersViewSet: Found {users.count()} registered users")
        
        for user in users:
            email = (user.email or '').lower().strip()
            if email and '@' in email:
                # Get phone from profile if exists
                phone = ''
                try:
                    profile = getattr(user, 'profile', None)
                    if profile:
                        phone = profile.phone or ''
                except Exception:
                    pass
                
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or email.split('@')[0]
                
                customers_dict[email] = {
                    'id': str(user.id),
                    'email': email,
                    'name': name,
                    'phone': phone,
                    'total_orders': 0,
                    'total_spent': 0,
                    'last_order': None,
                    'source': 'registered',
                    'status': 'active',
                    'tags': ['registered'],
                    'created_at': user.date_joined.isoformat() if user.date_joined else None,
                }
        
        # 2. Get customers from Store Orders
        order_customers = StoreOrder.objects.filter(
            store_id=store_id,
            customer_email__isnull=False
        ).exclude(
            customer_email=''
        ).values('customer_email', 'customer_name', 'customer_phone').annotate(
            total_orders=Count('id'),
            total_spent=Sum('total'),
            last_order=Max('created_at')
        )
            
            for customer in order_customers:
                email = customer['customer_email'].lower().strip()
                if email and '@' in email:
                    if email not in customers_dict:
                        customers_dict[email] = {
                            'id': email,
                            'email': email,
                            'name': customer['customer_name'] or '',
                            'phone': customer['customer_phone'] or '',
                            'total_orders': customer['total_orders'] or 0,
                            'total_spent': float(customer['total_spent'] or 0),
                            'last_order': customer['last_order'].isoformat() if customer['last_order'] else None,
                            'source': 'orders',
                            'status': 'active',
                            'tags': ['customer'],
                        }
                    else:
                        # Merge order data into existing customer
                        customers_dict[email]['total_orders'] = customer['total_orders'] or 0
                        customers_dict[email]['total_spent'] = float(customer['total_spent'] or 0)
                        customers_dict[email]['last_order'] = customer['last_order'].isoformat() if customer['last_order'] else None
                        if 'customer' not in customers_dict[email]['tags']:
                            customers_dict[email]['tags'].append('customer')
                        if not customers_dict[email]['name'] and customer['customer_name']:
                            customers_dict[email]['name'] = customer['customer_name']
                        if not customers_dict[email]['phone'] and customer['customer_phone']:
                            customers_dict[email]['phone'] = customer['customer_phone']
        
        # 3. Get subscribers from marketing
        subscribers = Subscriber.objects.filter(store_id=store_id)
        for sub in subscribers:
            email = sub.email.lower().strip()
            if email not in customers_dict:
                customers_dict[email] = {
                    'id': str(sub.id),
                    'email': email,
                    'name': sub.name or '',
                    'phone': sub.phone or '',
                    'total_orders': sub.total_orders or 0,
                    'total_spent': float(sub.total_spent or 0),
                    'last_order': None,
                    'source': sub.source or 'subscriber',
                    'status': sub.status,
                    'tags': sub.tags or [],
                }
            else:
                # Merge subscriber data
                if sub.status == 'unsubscribed':
                    customers_dict[email]['status'] = 'unsubscribed'
                if sub.tags:
                    for tag in sub.tags:
                        if tag not in customers_dict[email]['tags']:
                            customers_dict[email]['tags'].append(tag)
                if sub.name and not customers_dict[email]['name']:
                    customers_dict[email]['name'] = sub.name
        
        # Convert to list and sort
        customers_list = list(customers_dict.values())
        customers_list.sort(key=lambda x: (x['total_orders'], x.get('created_at', '')), reverse=True)
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            customers_list = [c for c in customers_list if c['status'] == status_filter]
        
        search = request.query_params.get('search', '').lower()
        if search:
            customers_list = [c for c in customers_list if 
                search in c['email'].lower() or 
                search in c['name'].lower() or
                search in (c['phone'] or '').lower()
            ]
        
        return Response({
            'count': len(customers_list),
            'results': customers_list,
        })
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """Get customer count for a store."""
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store, StoreOrder
        
        User = get_user_model()
        
        store_id = request.query_params.get('store')
        if not store_id:
            return Response({'count': 0})
        
        # Count registered users (non-staff)
        user_count = User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False
        ).count()
        
        # Count subscribers
        subscriber_count = Subscriber.objects.filter(store_id=store_id).count()
        
        # Count unique order emails
        try:
            Store.objects.get(id=store_id)
            order_emails = StoreOrder.objects.filter(
                store_id=store_id,
                customer_email__isnull=False
            ).exclude(customer_email='').values('customer_email').distinct().count()
        except Store.DoesNotExist:
            order_emails = 0
        
        # Return the highest count (users are the main source now)
        return Response({'count': max(user_count, subscriber_count, order_emails)})
    
    @action(detail=False, methods=['get'])
    def debug(self, request):
        """Debug endpoint to check data sources."""
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store, StoreOrder
        
        User = get_user_model()
        
        store_id = request.query_params.get('store')
        
        # Count all users
        all_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        staff_users = User.objects.filter(is_staff=True).count()
        superusers = User.objects.filter(is_superuser=True).count()
        customer_users = User.objects.filter(
            is_active=True
        ).exclude(is_staff=True).exclude(is_superuser=True).count()
        
        # Sample users (first 5 non-staff)
        sample_users = list(User.objects.filter(
            is_active=True
        ).exclude(is_staff=True).exclude(is_superuser=True).values(
            'id', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'date_joined'
        )[:5])
        
        # Subscribers count
        subscriber_count = Subscriber.objects.filter(store_id=store_id).count() if store_id else 0
        
        # Orders count
        order_count = 0
        if store_id:
            try:
                Store.objects.get(id=store_id)
                order_count = StoreOrder.objects.filter(
                    store_id=store_id,
                    customer_email__isnull=False
                ).exclude(customer_email='').count()
            except Store.DoesNotExist:
                pass
        
        return Response({
            'users': {
                'total': all_users,
                'active': active_users,
                'staff': staff_users,
                'superusers': superusers,
                'customers': customer_users,
                'sample': sample_users,
            },
            'subscribers': subscriber_count,
            'orders_with_email': order_count,
            'store_id': store_id,
        })


class MarketingStatsViewSet(viewsets.ViewSet):
    """ViewSet for marketing statistics."""
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Get marketing stats for a store."""
        store_id = request.query_params.get('store')
        
        if not store_id:
            return Response(
                {'error': 'store parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        stats = email_marketing_service.get_stats(store_id)
        return Response(stats)


class QuickActionsViewSet(viewsets.ViewSet):
    """ViewSet for quick marketing actions."""
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def send_coupon(self, request):
        """Send a coupon email."""
        serializer = SendCouponEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        store_id = request.data.get('store')
        if not store_id:
            return Response(
                {'error': 'store is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = email_marketing_service.send_coupon_email(
            store_id=store_id,
            to_email=serializer.validated_data['to_email'],
            customer_name=serializer.validated_data['customer_name'],
            coupon_code=serializer.validated_data['coupon_code'],
            discount_value=serializer.validated_data['discount_value'],
            expiry_date=serializer.validated_data.get('expiry_date'),
        )
        
        if result['success']:
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def send_welcome(self, request):
        """Send a welcome email."""
        serializer = SendWelcomeEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        store_id = request.data.get('store')
        if not store_id:
            return Response(
                {'error': 'store is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = email_marketing_service.send_welcome_email(
            store_id=store_id,
            to_email=serializer.validated_data['to_email'],
            customer_name=serializer.validated_data['customer_name'],
        )
        
        if result['success']:
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)


class EmailAutomationViewSet(viewsets.ModelViewSet):
    """ViewSet for email automations."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = EmailAutomationSerializer
    
    def get_queryset(self):
        queryset = EmailAutomation.objects.all()
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        trigger_type = self.request.query_params.get('trigger_type')
        if trigger_type:
            queryset = queryset.filter(trigger_type=trigger_type)
        return queryset.select_related('template', 'store')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailAutomationListSerializer
        return EmailAutomationSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def trigger_types(self, request):
        """Get available trigger types."""
        return Response([
            {'value': choice[0], 'label': choice[1]}
            for choice in EmailAutomation.TriggerType.choices
        ])
    
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle automation active status."""
        automation = self.get_object()
        automation.is_active = not automation.is_active
        automation.save(update_fields=['is_active'])
        return Response(EmailAutomationSerializer(automation).data)
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Get logs for this automation."""
        automation = self.get_object()
        logs = EmailAutomationLog.objects.filter(automation=automation)[:100]
        return Response(EmailAutomationLogSerializer(logs, many=True).data)
    
    @action(detail=False, methods=['post'])
    def trigger(self, request):
        """Manually trigger an automation."""
        serializer = TriggerAutomationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        store_id = request.data.get('store')
        if not store_id:
            return Response(
                {'error': 'store is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = email_automation_service.trigger(
            store_id=store_id,
            trigger_type=serializer.validated_data['trigger_type'],
            recipient_email=serializer.validated_data['recipient_email'],
            recipient_name=serializer.validated_data.get('recipient_name', ''),
            context=serializer.validated_data.get('context', {})
        )
        
        if result.get('success'):
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def test(self, request):
        """Send a test email for an automation."""
        automation_id = request.data.get('automation_id')
        test_email = request.data.get('email')
        
        if not automation_id or not test_email:
            return Response(
                {'error': 'automation_id and email are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            automation = EmailAutomation.objects.get(id=automation_id)
        except EmailAutomation.DoesNotExist:
            return Response(
                {'error': 'Automation not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Send test email
        result = email_automation_service.trigger(
            store_id=str(automation.store_id),
            trigger_type=automation.trigger_type,
            recipient_email=test_email,
            recipient_name='Teste',
            context={'is_test': True}
        )
        
        return Response(result)


class TemplateVariablesViewSet(viewsets.ViewSet):
    """ViewSet for template variables and preview."""
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get all available template variables with descriptions."""
        variables = {
            'customer': {
                'description': 'Variáveis do cliente (preenchidas automaticamente)',
                'variables': [
                    {'name': 'customer_name', 'description': 'Nome completo do cliente', 'example': 'João Silva'},
                    {'name': 'first_name', 'description': 'Primeiro nome do cliente', 'example': 'João'},
                    {'name': 'email', 'description': 'Email do cliente', 'example': 'joao@email.com'},
                    {'name': 'phone', 'description': 'Telefone do cliente', 'example': '(11) 99999-9999'},
                ]
            },
            'store': {
                'description': 'Variáveis da loja',
                'variables': [
                    {'name': 'store_name', 'description': 'Nome da loja', 'example': 'Pastita'},
                    {'name': 'store_url', 'description': 'URL da loja', 'example': 'https://pastita.com.br'},
                    {'name': 'year', 'description': 'Ano atual', 'example': '2026'},
                ]
            },
            'order': {
                'description': 'Variáveis de pedido (para automações de pedido)',
                'variables': [
                    {'name': 'order_number', 'description': 'Número do pedido', 'example': 'PAS-2026-001'},
                    {'name': 'order_total', 'description': 'Total do pedido', 'example': '89.90'},
                    {'name': 'order_status', 'description': 'Status do pedido', 'example': 'confirmed'},
                    {'name': 'delivery_method', 'description': 'Método de entrega', 'example': 'delivery'},
                    {'name': 'tracking_code', 'description': 'Código de rastreio', 'example': 'BR123456789'},
                    {'name': 'tracking_url', 'description': 'URL de rastreio', 'example': 'https://...'},
                ]
            },
            'coupon': {
                'description': 'Variáveis de cupom (para campanhas de cupom)',
                'variables': [
                    {'name': 'coupon_code', 'description': 'Código do cupom', 'example': 'DESCONTO10'},
                    {'name': 'discount_value', 'description': 'Valor do desconto', 'example': '10%'},
                    {'name': 'expiry_date', 'description': 'Data de expiração', 'example': '31/12/2026'},
                ]
            },
            'promotion': {
                'description': 'Variáveis de promoção',
                'variables': [
                    {'name': 'promotion_title', 'description': 'Título da promoção', 'example': 'Black Friday'},
                    {'name': 'promotion_description', 'description': 'Descrição da promoção', 'example': 'Até 50% OFF'},
                ]
            }
        }
        return Response(variables)
    
    @action(detail=False, methods=['post'])
    def preview(self, request):
        """Generate a preview of a template with sample data."""
        from apps.stores.models import Store
        from django.utils import timezone
        
        html_content = request.data.get('html_content', '')
        store_id = request.data.get('store')
        customer_email = request.data.get('customer_email')  # Optional: use real customer data
        
        if not html_content:
            return Response(
                {'error': 'html_content is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get store info
        store_name = 'Loja'
        store_url = 'https://loja.com.br'
        if store_id:
            try:
                store = Store.objects.get(id=store_id)
                store_name = store.name
                store_url = store.website_url or f'https://{store.slug}.com.br'
            except Store.DoesNotExist:
                pass
        
        # Get customer data if email provided
        customer_name = 'Cliente Exemplo'
        first_name = 'Cliente'
        email = 'cliente@exemplo.com'
        phone = '(11) 99999-9999'
        
        if customer_email:
            # Try to find real customer data
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            user = User.objects.filter(email=customer_email).first()
            if user:
                customer_name = f"{user.first_name} {user.last_name}".strip() or user.email.split('@')[0]
                first_name = user.first_name or user.email.split('@')[0]
                email = user.email
                try:
                    if hasattr(user, 'profile') and user.profile:
                        phone = user.profile.phone or phone
                except Exception:
                    pass
            else:
                # Try subscriber
                subscriber = Subscriber.objects.filter(email=customer_email).first()
                if subscriber:
                    customer_name = subscriber.name or customer_email.split('@')[0]
                    first_name = customer_name.split()[0] if customer_name else customer_email.split('@')[0]
                    email = subscriber.email
                    phone = subscriber.phone or phone
        
        # Build replacement variables
        variables = {
            # Customer
            'customer_name': customer_name,
            'name': customer_name,
            'first_name': first_name,
            'email': email,
            'phone': phone,
            # Store
            'store_name': store_name,
            'store_url': store_url,
            'year': str(timezone.now().year),
            # Order (sample)
            'order_number': 'PAS-2026-001',
            'order_total': '89.90',
            'order_status': 'confirmed',
            'delivery_method': 'delivery',
            'tracking_code': 'BR123456789',
            'tracking_url': 'https://rastreamento.correios.com.br',
            # Coupon (sample)
            'coupon_code': 'DESCONTO10',
            'discount_value': '10%',
            'expiry_date': '31/12/2026',
            # Promotion (sample)
            'promotion_title': 'Promoção Especial',
            'promotion_description': 'Aproveite descontos incríveis!',
        }
        
        # Replace variables in content
        preview_html = html_content
        for key, value in variables.items():
            preview_html = preview_html.replace(f'{{{{{key}}}}}', value)
            preview_html = preview_html.replace(f'{{{{ {key} }}}}', value)
        
        return Response({
            'preview_html': preview_html,
            'variables_used': variables,
        })
    
    @action(detail=False, methods=['get'])
    def sample_customer(self, request):
        """Get a sample customer for preview."""
        from django.contrib.auth import get_user_model
        
        store_id = request.query_params.get('store')
        
        # Try to get a real customer
        User = get_user_model()
        user = User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False
        ).exclude(email='').first()
        
        if user:
            phone = ''
            try:
                if hasattr(user, 'profile') and user.profile:
                    phone = user.profile.phone or ''
            except Exception:
                pass
            
            return Response({
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}".strip() or user.email.split('@')[0],
                'first_name': user.first_name or user.email.split('@')[0],
                'phone': phone,
            })
        
        # Fallback to subscriber
        if store_id:
            subscriber = Subscriber.objects.filter(store_id=store_id, status='active').first()
            if subscriber:
                return Response({
                    'email': subscriber.email,
                    'name': subscriber.name or subscriber.email.split('@')[0],
                    'first_name': (subscriber.name or subscriber.email.split('@')[0]).split()[0],
                    'phone': subscriber.phone or '',
                })
        
        # Return sample data
        return Response({
            'email': 'cliente@exemplo.com',
            'name': 'Cliente Exemplo',
            'first_name': 'Cliente',
            'phone': '(11) 99999-9999',
        })
