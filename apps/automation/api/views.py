"""
Automation API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from ..models import (
    CompanyProfile, AutoMessage, CustomerSession, AutomationLog,
    ScheduledMessage, ReportSchedule, GeneratedReport
)


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API results."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


from ..services import AutomationService
from .serializers import (
    CompanyProfileSerializer,
    CreateCompanyProfileSerializer,
    UpdateCompanyProfileSerializer,
    AutoMessageSerializer,
    CreateAutoMessageSerializer,
    CustomerSessionSerializer,
    AutomationLogSerializer,
    ScheduledMessageSerializer,
    CreateScheduledMessageSerializer,
    UpdateScheduledMessageSerializer,
    ReportScheduleSerializer,
    CreateReportScheduleSerializer,
    UpdateReportScheduleSerializer,
    GeneratedReportSerializer,
    GenerateReportSerializer,
)

logger = logging.getLogger(__name__)


class CompanyProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for CompanyProfile CRUD operations."""
    
    queryset = CompanyProfile.objects.select_related('account').filter(is_active=True)
    serializer_class = CompanyProfileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by account if provided
        account_id = self.request.query_params.get('account_id')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Filter by business type
        business_type = self.request.query_params.get('business_type')
        if business_type:
            queryset = queryset.filter(business_type=business_type)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new company profile."""
        serializer = CreateCompanyProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = AutomationService()
        profile = service.create_company_profile(**serializer.validated_data)
        
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


class AutoMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for AutoMessage CRUD operations."""
    
    queryset = AutoMessage.objects.select_related('company').filter(is_active=True)
    serializer_class = AutoMessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
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


class CustomerSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for CustomerSession (read-only with actions)."""
    
    queryset = CustomerSession.objects.select_related('company', 'conversation', 'order').filter(is_active=True)
    serializer_class = CustomerSessionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by company
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Filter by status
        session_status = self.request.query_params.get('status')
        if session_status:
            queryset = queryset.filter(status=session_status)
        
        # Filter by phone number
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset.order_by('-last_activity_at')
    
    @action(detail=False, methods=['get'])
    def by_phone(self, request):
        """Get sessions by phone number."""
        phone_number = request.query_params.get('phone_number')
        company_id = request.query_params.get('company_id')
        
        if not phone_number:
            return Response(
                {'error': 'phone_number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(phone_number=phone_number)
        
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_notification(self, request, pk=None):
        """Manually send a notification to a session."""
        session = self.get_object()
        event_type = request.data.get('event_type')
        
        if not event_type:
            return Response(
                {'error': 'event_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get additional context
        context = request.data.get('context', {})
        
        service = AutomationService()
        success = service._send_notification(
            session.company,
            session,
            event_type,
            context
        )
        
        if success:
            return Response({
                'success': True,
                'message': f'Notification {event_type} sent successfully'
            })
        else:
            return Response({
                'success': False,
                'message': 'Failed to send notification or already sent'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update session status."""
        session = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'error': 'status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_statuses = [s[0] for s in CustomerSession.SessionStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session.status = new_status
        session.save(update_fields=['status'])
        
        return Response(CustomerSessionSerializer(session).data)


class AutomationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for AutomationLog (read-only)."""
    
    queryset = AutomationLog.objects.select_related('company', 'session')
    serializer_class = AutomationLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by company
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Filter by action type
        action_type = self.request.query_params.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        
        # Filter by error status
        is_error = self.request.query_params.get('is_error')
        if is_error is not None:
            queryset = queryset.filter(is_error=is_error.lower() == 'true')
        
        # Filter by phone number
        phone_number = self.request.query_params.get('phone_number')
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get log statistics."""
        company_id = request.query_params.get('company_id')
        
        queryset = self.get_queryset()
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        
        # Time ranges
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        
        # Stats by action type
        by_action = queryset.values('action_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Stats by day (last 7 days)
        by_day = []
        for i in range(7):
            day_start = today_start - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            count = queryset.filter(
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            by_day.append({
                'date': day_start.date().isoformat(),
                'count': count
            })
        
        # Error rate
        total = queryset.count()
        errors = queryset.filter(is_error=True).count()
        error_rate = (errors / total * 100) if total > 0 else 0
        
        return Response({
            'total': total,
            'today': queryset.filter(created_at__gte=today_start).count(),
            'this_week': queryset.filter(created_at__gte=week_start).count(),
            'errors': errors,
            'error_rate': round(error_rate, 2),
            'by_action_type': list(by_action),
            'by_day': by_day,
        })


class ScheduledMessageViewSet(viewsets.ModelViewSet):
    """ViewSet for ScheduledMessage CRUD operations."""
    
    queryset = ScheduledMessage.objects.select_related('account', 'created_by').filter(is_active=True)
    serializer_class = ScheduledMessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by account
        account_id = self.request.query_params.get('account_id')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Filter by status
        msg_status = self.request.query_params.get('status')
        if msg_status:
            queryset = queryset.filter(status=msg_status)
        
        # Filter by message type
        message_type = self.request.query_params.get('message_type')
        if message_type:
            queryset = queryset.filter(message_type=message_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(scheduled_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(scheduled_at__lte=end_date)
        
        return queryset.order_by('scheduled_at')
    
    def create(self, request, *args, **kwargs):
        """Create a new scheduled message."""
        serializer = CreateScheduledMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id')
        
        from apps.whatsapp.models import WhatsAppAccount
        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return Response(
                {'error': 'WhatsApp account not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        scheduled_message = ScheduledMessage.objects.create(
            account=account,
            created_by=request.user,
            **data
        )
        
        return Response(
            ScheduledMessageSerializer(scheduled_message).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a scheduled message."""
        instance = self.get_object()
        
        # Can only update pending messages
        if instance.status != ScheduledMessage.Status.PENDING:
            return Response(
                {'error': 'Can only update pending messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = UpdateScheduledMessageSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        for key, value in serializer.validated_data.items():
            setattr(instance, key, value)
        
        instance.save()
        return Response(ScheduledMessageSerializer(instance).data)
    
    def destroy(self, request, *args, **kwargs):
        """Cancel a scheduled message."""
        instance = self.get_object()
        
        if instance.status == ScheduledMessage.Status.PENDING:
            instance.status = ScheduledMessage.Status.CANCELLED
            instance.save(update_fields=['status'])
        else:
            instance.is_active = False
            instance.save(update_fields=['is_active'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending scheduled message."""
        instance = self.get_object()
        
        if instance.status != ScheduledMessage.Status.PENDING:
            return Response(
                {'error': 'Can only cancel pending messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.status = ScheduledMessage.Status.CANCELLED
        instance.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Scheduled message cancelled'
        })
    
    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Reschedule a message."""
        instance = self.get_object()
        new_scheduled_at = request.data.get('scheduled_at')
        
        if not new_scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if instance.status not in [ScheduledMessage.Status.PENDING, ScheduledMessage.Status.FAILED]:
            return Response(
                {'error': 'Can only reschedule pending or failed messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils.dateparse import parse_datetime
        parsed_date = parse_datetime(new_scheduled_at)
        if not parsed_date:
            return Response(
                {'error': 'Invalid datetime format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.scheduled_at = parsed_date
        instance.status = ScheduledMessage.Status.PENDING
        instance.error_message = ''
        instance.save()
        
        return Response(ScheduledMessageSerializer(instance).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get scheduled message statistics."""
        account_id = request.query_params.get('account_id')
        
        queryset = self.get_queryset()
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return Response({
            'total': queryset.count(),
            'pending': queryset.filter(status=ScheduledMessage.Status.PENDING).count(),
            'sent': queryset.filter(status=ScheduledMessage.Status.SENT).count(),
            'failed': queryset.filter(status=ScheduledMessage.Status.FAILED).count(),
            'cancelled': queryset.filter(status=ScheduledMessage.Status.CANCELLED).count(),
            'scheduled_today': queryset.filter(
                status=ScheduledMessage.Status.PENDING,
                scheduled_at__gte=today_start,
                scheduled_at__lt=today_start + timedelta(days=1)
            ).count(),
            'sent_today': queryset.filter(
                status=ScheduledMessage.Status.SENT,
                sent_at__gte=today_start
            ).count(),
        })


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """ViewSet for ReportSchedule CRUD operations."""
    
    queryset = ReportSchedule.objects.select_related('account', 'company', 'created_by').filter(is_active=True)
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        schedule_status = self.request.query_params.get('status')
        if schedule_status:
            queryset = queryset.filter(status=schedule_status)
        
        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        # Filter by frequency
        frequency = self.request.query_params.get('frequency')
        if frequency:
            queryset = queryset.filter(frequency=frequency)
        
        return queryset.order_by('name')
    
    def create(self, request, *args, **kwargs):
        """Create a new report schedule."""
        serializer = CreateReportScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id', None)
        company_id = data.pop('company_id', None)
        
        schedule = ReportSchedule.objects.create(
            account_id=account_id,
            company_id=company_id,
            created_by=request.user,
            **data
        )
        
        # Calculate next run
        schedule.calculate_next_run()
        schedule.save()
        
        return Response(
            ReportScheduleSerializer(schedule).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a report schedule."""
        instance = self.get_object()
        serializer = UpdateReportScheduleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        account_id = data.pop('account_id', None)
        company_id = data.pop('company_id', None)
        
        if account_id is not None:
            instance.account_id = account_id
        if company_id is not None:
            instance.company_id = company_id
        
        for key, value in data.items():
            setattr(instance, key, value)
        
        # Recalculate next run if schedule changed
        if any(k in data for k in ['frequency', 'day_of_week', 'day_of_month', 'hour', 'timezone']):
            instance.calculate_next_run()
        
        instance.save()
        return Response(ReportScheduleSerializer(instance).data)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a report schedule."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """Run a report immediately."""
        schedule = self.get_object()
        
        from ..tasks import generate_report
        task = generate_report.delay(schedule_id=str(schedule.id))
        
        return Response({
            'success': True,
            'message': 'Report generation started',
            'task_id': task.id
        })
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a report schedule."""
        schedule = self.get_object()
        schedule.status = ReportSchedule.Status.PAUSED
        schedule.save(update_fields=['status'])
        
        return Response({
            'success': True,
            'message': 'Report schedule paused'
        })
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a paused report schedule."""
        schedule = self.get_object()
        schedule.status = ReportSchedule.Status.ACTIVE
        schedule.calculate_next_run()
        schedule.save()
        
        return Response({
            'success': True,
            'message': 'Report schedule resumed'
        })


class GeneratedReportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for GeneratedReport (read-only)."""
    
    queryset = GeneratedReport.objects.select_related('schedule', 'created_by')
    serializer_class = GeneratedReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by schedule
        schedule_id = self.request.query_params.get('schedule_id')
        if schedule_id:
            queryset = queryset.filter(schedule_id=schedule_id)
        
        # Filter by status
        report_status = self.request.query_params.get('status')
        if report_status:
            queryset = queryset.filter(status=report_status)
        
        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate a report on demand."""
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        from ..tasks import generate_report
        task = generate_report.delay(
            report_type=data.get('report_type', 'full'),
            period_start=data.get('period_start', '').isoformat() if data.get('period_start') else None,
            period_end=data.get('period_end', '').isoformat() if data.get('period_end') else None,
            account_id=str(data.get('account_id')) if data.get('account_id') else None,
            company_id=str(data.get('company_id')) if data.get('company_id') else None,
            recipients=data.get('recipients', []),
            export_format=data.get('export_format', 'xlsx'),
            user_id=request.user.id
        )
        
        return Response({
            'success': True,
            'message': 'Report generation started',
            'task_id': task.id
        })
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download a generated report."""
        import os
        from django.http import FileResponse
        
        report = self.get_object()
        
        if report.status != GeneratedReport.Status.COMPLETED:
            return Response(
                {'error': 'Report not ready for download'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not report.file_path or not os.path.exists(report.file_path):
            return Response(
                {'error': 'Report file not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return FileResponse(
            open(report.file_path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(report.file_path)
        )
    
    @action(detail=True, methods=['post'])
    def resend_email(self, request, pk=None):
        """Resend report email."""
        report = self.get_object()
        recipients = request.data.get('recipients', report.email_recipients)
        
        if not recipients:
            return Response(
                {'error': 'No recipients specified'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from ..tasks.scheduled import _send_report_email
        _send_report_email(report, recipients)
        
        return Response({
            'success': True,
            'message': f'Report email sent to {recipients}'
        })
