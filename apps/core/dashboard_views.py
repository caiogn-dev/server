"""
Dashboard API views - Aggregated metrics and statistics.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.whatsapp.models import WhatsAppAccount, Message, WebhookEvent
from apps.conversations.models import Conversation
from apps.stores.models import StoreOrder, Store
from apps.langflow.models import LangflowFlow, LangflowSession, LangflowLog
from apps.core.services.dashboard_stats import DashboardStatsAggregator

logger = logging.getLogger(__name__)


class DashboardOverviewView(APIView):
    """Dashboard overview with key metrics."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dashboard Overview",
        description="Get aggregated metrics for dashboard",
        responses={200: dict}
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        # Base querysets
        accounts_qs = WhatsAppAccount.objects.filter(is_active=True)
        if account_id:
            accounts_qs = accounts_qs.filter(id=account_id)
        
        account_ids = list(accounts_qs.values_list('id', flat=True))
        
        messages_qs = Message.objects.filter(account_id__in=account_ids)
        conversations_qs = Conversation.objects.filter(account_id__in=account_ids)
        orders_qs = StoreOrder.objects.filter(is_active=True)
        store_param = request.query_params.get('store')
        if store_param:
            try:
                import uuid as uuid_module
                uuid_module.UUID(store_param)
                orders_qs = orders_qs.filter(store_id=store_param)
            except (ValueError, AttributeError):
                orders_qs = orders_qs.filter(store__slug=store_param)
        
        # Messages metrics
        messages_today = messages_qs.filter(created_at__gte=today_start).count()
        messages_week = messages_qs.filter(created_at__gte=week_start).count()
        messages_month = messages_qs.filter(created_at__gte=month_start).count()
        
        messages_by_status = dict(
            messages_qs.filter(created_at__gte=today_start)
            .values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        messages_by_direction = dict(
            messages_qs.filter(created_at__gte=today_start)
            .values('direction')
            .annotate(count=Count('id'))
            .values_list('direction', 'count')
        )

        # Conversations metrics
        conversations_active = conversations_qs.filter(
            status__in=['open', 'pending']
        ).count()
        
        conversations_by_status = dict(
            conversations_qs.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        conversations_by_mode = dict(
            conversations_qs.filter(status='open')
            .values('mode')
            .annotate(count=Count('id'))
            .values_list('mode', 'count')
        )
        
        conversations_resolved_today = conversations_qs.filter(
            resolved_at__gte=today_start
        ).count()

        # Orders metrics
        orders_by_status = dict(
            orders_qs.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        orders_today = orders_qs.filter(created_at__gte=today_start).count()
        
        revenue_today = orders_qs.filter(
            paid_at__gte=today_start
        ).aggregate(total=Sum('total'))['total'] or 0
        
        revenue_month = orders_qs.filter(
            paid_at__gte=month_start
        ).aggregate(total=Sum('total'))['total'] or 0

        # Payments metrics (derived from store orders)
        payments_pending = orders_qs.filter(
            payment_status__in=['pending', 'processing']
        ).count()
        
        payments_completed_today = orders_qs.filter(
            payment_status='paid',
            paid_at__gte=today_start
        ).count()

        # Langflow metrics
        langflow_logs_qs = LangflowLog.objects.filter(
            flow__accounts__id__in=account_ids
        ).distinct()
        
        langflow_interactions_today = langflow_logs_qs.filter(
            created_at__gte=today_start
        ).count()
        
        langflow_avg_duration = langflow_logs_qs.filter(
            created_at__gte=today_start,
            duration_ms__isnull=False
        ).aggregate(avg=Avg('duration_ms'))['avg'] or 0
        
        langflow_success_rate = 0
        langflow_total = langflow_logs_qs.filter(created_at__gte=today_start).count()
        if langflow_total > 0:
            langflow_success = langflow_logs_qs.filter(
                created_at__gte=today_start,
                status='success'
            ).count()
            langflow_success_rate = round((langflow_success / langflow_total) * 100, 1)

        # Accounts summary
        accounts_summary = {
            'total': accounts_qs.count(),
            'active': accounts_qs.filter(status='active').count(),
            'inactive': accounts_qs.filter(status='inactive').count(),
        }

        return Response({
            'accounts': accounts_summary,
            'messages': {
                'today': messages_today,
                'week': messages_week,
                'month': messages_month,
                'by_status': messages_by_status,
                'by_direction': messages_by_direction,
            },
            'conversations': {
                'active': conversations_active,
                'by_status': conversations_by_status,
                'by_mode': conversations_by_mode,
                'resolved_today': conversations_resolved_today,
            },
            'orders': {
                'today': orders_today,
                'by_status': orders_by_status,
                'revenue_today': float(revenue_today),
                'revenue_month': float(revenue_month),
            },
            'payments': {
                'pending': payments_pending,
                'completed_today': payments_completed_today,
            },
            'langflow': {
                'interactions_today': langflow_interactions_today,
                'avg_duration_ms': round(langflow_avg_duration, 2),
                'success_rate': langflow_success_rate,
            },
            'timestamp': now.isoformat(),
        })


class DashboardStatsView(APIView):
    """Single-query dashboard summary (today/week/month)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dashboard stats summary",
        description="Return pre-aggregated totals for today, week and month for a single store.",
        responses={
            200: dict,
            400: dict,
            404: dict,
        }
    )
    def get(self, request):
        store_param = (
            request.query_params.get('store_id')
            or request.query_params.get('store_slug')
            or request.query_params.get('store')
        )
        if not store_param:
            return Response(
                {'detail': 'store_id or store slug query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        store = self._resolve_store(store_param)
        if not store:
            return Response({'detail': 'Store not found.'}, status=status.HTTP_404_NOT_FOUND)

        payload = DashboardStatsAggregator(store).build_payload()
        return Response(payload)

    @staticmethod
    def _resolve_store(identifier: str) -> Optional[Store]:
        try:
            return Store.objects.get(id=uuid.UUID(identifier))
        except (ValueError, Store.DoesNotExist):
            return Store.objects.filter(slug=identifier).first()


class DashboardActivityView(APIView):
    """Recent activity feed for dashboard."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dashboard Activity",
        description="Get recent activity feed",
        responses={200: dict}
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        limit = int(request.query_params.get('limit', 20))
        
        accounts_qs = WhatsAppAccount.objects.filter(is_active=True)
        if account_id:
            accounts_qs = accounts_qs.filter(id=account_id)
        
        account_ids = list(accounts_qs.values_list('id', flat=True))

        orders_qs = StoreOrder.objects.filter(is_active=True)
        store_param = request.query_params.get('store')
        if store_param:
            try:
                import uuid as uuid_module
                uuid_module.UUID(store_param)
                orders_qs = orders_qs.filter(store_id=store_param)
            except (ValueError, AttributeError):
                orders_qs = orders_qs.filter(store__slug=store_param)

        # Recent messages
        recent_messages = Message.objects.filter(
            account_id__in=account_ids,
            direction='inbound'
        ).select_related('account').order_by('-created_at')[:limit]
        
        messages_data = [{
            'id': str(m.id),
            'type': 'message',
            'account_name': m.account.name,
            'from_number': m.from_number,
            'text': m.text_body[:100] if m.text_body else f'[{m.message_type}]',
            'message_type': m.message_type,
            'created_at': m.created_at.isoformat(),
        } for m in recent_messages]
        
        # Recent orders
        recent_orders = orders_qs.select_related('store').order_by('-created_at')[:limit]
        
        orders_data = [{
            'id': str(o.id),
            'type': 'order',
            'store_name': o.store.name,
            'order_number': o.order_number,
            'customer_name': o.customer_name,
            'customer_phone': o.customer_phone,
            'status': o.status,
            'total': float(o.total),
            'created_at': o.created_at.isoformat(),
        } for o in recent_orders]
        
        # Recent conversations
        recent_conversations = Conversation.objects.filter(
            account_id__in=account_ids,
            is_active=True
        ).select_related('account').order_by('-last_message_at')[:limit]
        
        conversations_data = [{
            'id': str(c.id),
            'type': 'conversation',
            'account_name': c.account.name,
            'phone_number': c.phone_number,
            'contact_name': c.contact_name,
            'status': c.status,
            'mode': c.mode,
            'last_message_at': c.last_message_at.isoformat() if c.last_message_at else None,
        } for c in recent_conversations]
        
        # Combine and sort by timestamp
        all_activity = messages_data + orders_data + conversations_data
        all_activity.sort(key=lambda x: x.get('created_at') or x.get('last_message_at') or '', reverse=True)
        
        return Response({
            'activity': all_activity[:limit],
            'messages': messages_data,
            'orders': orders_data,
            'conversations': conversations_data,
        })


class DashboardChartsView(APIView):
    """Chart data for dashboard."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dashboard Charts Data",
        description="Get data for dashboard charts",
        responses={200: dict}
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        days = int(request.query_params.get('days', 7))
        
        accounts_qs = WhatsAppAccount.objects.filter(is_active=True)
        if account_id:
            accounts_qs = accounts_qs.filter(id=account_id)
        
        account_ids = list(accounts_qs.values_list('id', flat=True))
        orders_qs = StoreOrder.objects.filter(is_active=True)
        store_param = request.query_params.get('store')
        if store_param:
            try:
                import uuid as uuid_module
                uuid_module.UUID(store_param)
                orders_qs = orders_qs.filter(store_id=store_param)
            except (ValueError, AttributeError):
                orders_qs = orders_qs.filter(store__slug=store_param)
        
        now = timezone.now()
        start_date = now - timedelta(days=days)
        
        # Messages per day
        messages_per_day = []
        for i in range(days):
            day_start = (now - timedelta(days=days-1-i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            inbound = Message.objects.filter(
                account_id__in=account_ids,
                direction='inbound',
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            outbound = Message.objects.filter(
                account_id__in=account_ids,
                direction='outbound',
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            messages_per_day.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'inbound': inbound,
                'outbound': outbound,
                'total': inbound + outbound,
            })
        
        # Orders per day
        orders_per_day = []
        for i in range(days):
            day_start = (now - timedelta(days=days-1-i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = orders_qs.filter(
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            revenue = orders_qs.filter(
                paid_at__gte=day_start,
                paid_at__lt=day_end
            ).aggregate(total=Sum('total'))['total'] or 0
            
            orders_per_day.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'count': count,
                'revenue': float(revenue),
            })
        
        # Conversations per day
        conversations_per_day = []
        for i in range(days):
            day_start = (now - timedelta(days=days-1-i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            new_conversations = Conversation.objects.filter(
                account_id__in=account_ids,
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            resolved = Conversation.objects.filter(
                account_id__in=account_ids,
                resolved_at__gte=day_start,
                resolved_at__lt=day_end
            ).count()
            
            conversations_per_day.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'new': new_conversations,
                'resolved': resolved,
            })
        
        # Message types distribution
        message_types = dict(
            Message.objects.filter(
                account_id__in=account_ids,
                created_at__gte=start_date
            ).values('message_type')
            .annotate(count=Count('id'))
            .values_list('message_type', 'count')
        )
        
        # Order status distribution
        order_statuses = dict(
            orders_qs.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        return Response({
            'messages_per_day': messages_per_day,
            'orders_per_day': orders_per_day,
            'conversations_per_day': conversations_per_day,
            'message_types': message_types,
            'order_statuses': order_statuses,
        })
