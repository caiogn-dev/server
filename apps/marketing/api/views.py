"""
Marketing API views.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from apps.marketing.models import EmailTemplate, EmailCampaign, EmailRecipient, Subscriber
from apps.marketing.services import email_marketing_service
from .serializers import (
    EmailTemplateSerializer, EmailTemplateListSerializer,
    EmailCampaignSerializer, EmailCampaignListSerializer,
    EmailRecipientSerializer, SubscriberSerializer, SubscriberListSerializer,
    MarketingStatsSerializer, SendCouponEmailSerializer, SendWelcomeEmailSerializer,
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
        result = email_marketing_service.send_campaign(pk)
        if result['success']:
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)
    
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
