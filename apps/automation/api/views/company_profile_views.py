"""
Company Profile API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from apps.automation.models import (
    CompanyProfile, AutoMessage, CustomerSession, AutomationLog
)
from apps.automation.services import AutomationService
from apps.automation.api.serializers import (
    CompanyProfileSerializer,
    CreateCompanyProfileSerializer,
    UpdateCompanyProfileSerializer,
)
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class CompanyProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for CompanyProfile CRUD operations."""
    
    queryset = CompanyProfile.objects.select_related('account', 'store').filter(is_active=True)
    serializer_class = CompanyProfileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's stores or accounts
        # Users should only see profiles for stores they own/manage or accounts they own
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(store__owner=user) | 
                Q(store__staff=user) | 
                Q(account__owner=user)
            ).distinct()
        
        # Filter by account if provided
        account_id = self.request.query_params.get('account_id')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Filter by store if provided
        store_slug = self.request.query_params.get('store_slug')
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        
        # Filter by business type
        business_type = self.request.query_params.get('business_type')
        if business_type:
            queryset = queryset.filter(_business_type=business_type)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def store_data(self, request):
        """
        Get store data for pre-filling company profile.
        Returns store information based on account_id or store_slug.
        """
        account_id = request.query_params.get('account_id')
        store_slug = request.query_params.get('store_slug')
        
        if not account_id and not store_slug:
            return Response(
                {'error': 'account_id or store_slug is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from apps.stores.models import Store
            
            # Try to find store by slug first
            if store_slug:
                store = Store.objects.get(slug=store_slug, is_active=True)
            else:
                # Try to find store by WhatsApp account
                from apps.whatsapp.models import WhatsAppAccount
                account = WhatsAppAccount.objects.get(id=account_id)
                
                # Look for store with matching whatsapp_number
                store = Store.objects.filter(
                    whatsapp_number=account.phone_number,
                    is_active=True
                ).first()
                
                if not store:
                    # Try by owner
                    store = Store.objects.filter(
                        owner=account.owner,
                        is_active=True
                    ).first()
            
            if not store:
                return Response(
                    {'error': 'Store not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Build business hours from store.operating_hours
            business_hours = {}
            if store.operating_hours:
                day_map = {
                    'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
                    'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
                }
                for day, hours in store.operating_hours.items():
                    short_day = day_map.get(day.lower(), day.lower()[:3])
                    business_hours[short_day] = {
                        'open': hours.get('open', '09:00'),
                        'close': hours.get('close', '18:00'),
                        'closed': hours.get('open') == '' or hours.get('close') == ''
                    }
            
            # Map store type to business type
            business_type_map = {
                'food': 'restaurant',
                'retail': 'retail',
                'services': 'services',
                'digital': 'ecommerce',
                'other': 'other'
            }
            
            data = {
                'company_name': store.name,
                'business_type': business_type_map.get(store.store_type, 'other'),
                'description': store.description or '',
                'website_url': '',  # Can be filled from integrations
                'menu_url': f"https://{store.slug}.pastita.com.br" if hasattr(store, 'slug') else '',
                'order_url': f"https://{store.slug}.pastita.com.br/cardapio" if hasattr(store, 'slug') else '',
                'business_hours': business_hours,
                'phone_number': store.whatsapp_number or store.phone or '',
                'email': store.email or '',
                'address': store.address or '',
                'city': store.city or '',
                'state': store.state or '',
                'store_id': str(store.id),
                'store_slug': store.slug,
            }
            
            return Response(data)
            
        except Exception as e:
            logger.error(f"Error fetching store data: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Create a new company profile.
        
        If store_id is provided, automatically populates business data from Store.
        Manual fields can override store data.
        """
        serializer = CreateCompanyProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data.copy()
        store_id = data.pop('store_id', None)
        
        # If store_id provided, fetch store data
        if store_id:
            try:
                from apps.stores.models import Store
                store = Store.objects.get(id=store_id, is_active=True)
                
                # Auto-populate from store if not manually provided
                if not data.get('company_name'):
                    data['company_name'] = store.name
                if not data.get('description'):
                    data['description'] = store.description or ''
                if not data.get('menu_url'):
                    data['menu_url'] = f"https://{store.slug}.pastita.com.br"
                if not data.get('order_url'):
                    data['order_url'] = f"https://{store.slug}.pastita.com.br/cardapio"
                
                # Map store_type to business_type
                if not data.get('business_type'):
                    type_mapping = {
                        'food': 'restaurant',
                        'retail': 'retail',
                        'services': 'services',
                        'digital': 'ecommerce',
                    }
                    data['business_type'] = type_mapping.get(store.store_type, 'other')
                
                # Convert operating_hours to business_hours
                if not data.get('business_hours') and store.operating_hours:
                    day_map = {
                        'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
                        'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
                    }
                    business_hours = {}
                    for day, hours in store.operating_hours.items():
                        short_day = day_map.get(day.lower(), day.lower()[:3])
                        business_hours[short_day] = {
                            'open': hours.get('open', '09:00'),
                            'close': hours.get('close', '18:00'),
                            'closed': not hours.get('open') or not hours.get('close')
                        }
                    data['business_hours'] = business_hours
                
                # Create profile with store
                service = AutomationService()
                profile = service.create_company_profile(**data)
                
            except Store.DoesNotExist:
                return Response(
                    {'error': 'Store not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {'error': 'store_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            CompanyProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a company profile."""
        instance = self.get_object()
        serializer = UpdateCompanyProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        service = AutomationService()
        profile = service.update_company_profile(
            profile_id=str(instance.id),
            **serializer.validated_data
        )
        
        return Response(CompanyProfileSerializer(profile).data)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a company profile."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def regenerate_api_key(self, request, pk=None):
        """Generate a new API key for the company."""
        profile = self.get_object()
        new_key = profile.generate_api_key()
        return Response({
            'api_key': new_key,
            'message': 'API key regenerated successfully'
        })
    
    @action(detail=True, methods=['post'])
    def regenerate_webhook_secret(self, request, pk=None):
        """Generate a new webhook secret for the company."""
        profile = self.get_object()
        new_secret = profile.generate_webhook_secret()
        return Response({
            'webhook_secret': new_secret,
            'message': 'Webhook secret regenerated successfully'
        })
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get statistics for a company profile."""
        profile = self.get_object()
        
        # Time ranges
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        # Session stats
        sessions = CustomerSession.objects.filter(company=profile, is_active=True)
        
        session_stats = {
            'total': sessions.count(),
            'active': sessions.filter(status='active').count(),
            'cart_created': sessions.filter(status='cart_created').count(),
            'cart_abandoned': sessions.filter(status='cart_abandoned').count(),
            'payment_pending': sessions.filter(status='payment_pending').count(),
            'completed': sessions.filter(status='completed').count(),
        }
        
        # Log stats
        logs = AutomationLog.objects.filter(company=profile)
        
        log_stats = {
            'total': logs.count(),
            'today': logs.filter(created_at__gte=today_start).count(),
            'errors': logs.filter(is_error=True).count(),
            'messages_sent': logs.filter(action_type='message_sent').count(),
            'webhooks_received': logs.filter(action_type='webhook_received').count(),
        }
        
        # Auto message stats
        auto_messages = AutoMessage.objects.filter(company=profile)
        
        message_stats = {
            'total': auto_messages.count(),
            'active': auto_messages.filter(is_active=True).count(),
        }
        
        # Cart recovery stats
        abandoned = sessions.filter(status='cart_abandoned').count()
        recovered = sessions.filter(
            status__in=['payment_confirmed', 'completed'],
            notifications_sent__contains=[{'type': 'cart_abandoned'}]
        ).count()
        
        recovery_rate = (recovered / abandoned * 100) if abandoned > 0 else 0
        
        return Response({
            'sessions': session_stats,
            'logs': log_stats,
            'auto_messages': message_stats,
            'cart_recovery': {
                'abandoned': abandoned,
                'recovered': recovered,
                'recovery_rate': round(recovery_rate, 2),
            }
        })
