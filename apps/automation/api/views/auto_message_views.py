"""
Auto Message API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from apps.automation.models import CompanyProfile, AutoMessage
from apps.automation.api.serializers import (
    AutoMessageSerializer,
    CreateAutoMessageSerializer,
    UpdateAutoMessageSerializer,
)
from .base import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class AutoMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for AutoMessage CRUD operations."""
    
    queryset = AutoMessage.objects.select_related('company', 'company__store', 'company__account').filter(is_active=True)
    serializer_class = AutoMessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Security: Filter by user's stores or accounts
        if not user.is_superuser:
            queryset = queryset.filter(
                Q(company__store__owner=user) | 
                Q(company__store__staff=user) | 
                Q(company__account__owner=user)
            ).distinct()
        
        # Filter by company
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Filter by event type
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.order_by('company', 'event_type', 'priority')
    
    def create(self, request, *args, **kwargs):
        """Create a new auto message."""
        serializer = CreateAutoMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        company_id = data.pop('company_id')
        
        try:
            company = CompanyProfile.objects.get(id=company_id, is_active=True)
        except CompanyProfile.DoesNotExist:
            return Response(
                {'error': 'Company profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        auto_message = AutoMessage.objects.create(company=company, **data)
        
        return Response(
            AutoMessageSerializer(auto_message).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update an auto message."""
        instance = self.get_object()
        serializer = UpdateAutoMessageSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # Update only provided fields
        data = serializer.validated_data
        for field, value in data.items():
            setattr(instance, field, value)
        
        instance.save()
        
        return Response(
            AutoMessageSerializer(instance).data
        )
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete an auto message."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test sending an auto message."""
        auto_message = self.get_object()
        phone_number = request.data.get('phone_number')
        
        if not phone_number:
            return Response(
                {'error': 'phone_number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build test context
        context = {
            'customer_name': request.data.get('customer_name', 'Cliente Teste'),
            'phone_number': phone_number,
            'cart_total': request.data.get('cart_total', '99.90'),
            'order_number': request.data.get('order_number', 'TEST-001'),
            'amount': request.data.get('amount', '99.90'),
            'pix_code': request.data.get('pix_code', '00020126580014br.gov.bcb.pix...'),
            'tracking_code': request.data.get('tracking_code', 'BR123456789'),
            'delivery_estimate': request.data.get('delivery_estimate', '40 minutos'),
            'company_name': auto_message.company.company_name,
            'website_url': auto_message.company.website_url,
            'menu_url': auto_message.company.menu_url,
        }
        
        # Render message
        rendered_message = auto_message.render_message(context)
        
        # Optionally send the message
        send = request.data.get('send', False)
        if send:
            from apps.whatsapp.services import MessageService
            service = MessageService()
            
            try:
                if auto_message.buttons:
                    service.send_interactive_buttons(
                        account_id=str(auto_message.company.account_id),
                        to=phone_number,
                        body_text=rendered_message,
                        buttons=auto_message.buttons
                    )
                else:
                    service.send_text_message(
                        account_id=str(auto_message.company.account_id),
                        to=phone_number,
                        text=rendered_message
                    )
                
                return Response({
                    'success': True,
                    'message': 'Test message sent',
                    'rendered_message': rendered_message,
                    'buttons': auto_message.buttons,
                })
            except Exception as e:
                return Response({
                    'success': False,
                    'error': str(e),
                    'rendered_message': rendered_message,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': True,
            'message': 'Message preview generated',
            'rendered_message': rendered_message,
            'buttons': auto_message.buttons,
        })
    
    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update auto messages."""
        updates = request.data.get('updates', [])
        
        if not updates:
            return Response(
                {'error': 'No updates provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_count = 0
        errors = []
        
        for update in updates:
            message_id = update.get('id')
            if not message_id:
                continue
            
            try:
                auto_message = AutoMessage.objects.get(id=message_id)
                
                for field in ['is_active', 'priority', 'message_text', 'delay_seconds']:
                    if field in update:
                        setattr(auto_message, field, update[field])
                
                auto_message.save()
                updated_count += 1
            except AutoMessage.DoesNotExist:
                errors.append(f"Message {message_id} not found")
            except Exception as e:
                errors.append(f"Error updating {message_id}: {str(e)}")
        
        return Response({
            'updated': updated_count,
            'errors': errors,
        })
