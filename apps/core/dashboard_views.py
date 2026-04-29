"""
Dashboard API views - Aggregated metrics and statistics.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q, F
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.whatsapp.models import WhatsAppAccount, Message, WebhookEvent
from apps.conversations.models import Conversation
from apps.stores.models import StoreOrder, Store, StoreProduct
from apps.agents.models import Agent, AgentConversation, AgentMessage
from apps.core.services.dashboard_stats import DashboardStatsAggregator

logger = logging.getLogger(__name__)


def _accessible_accounts(user):
    """WhatsApp accounts visible to current user."""
    queryset = WhatsAppAccount.objects.filter(is_active=True)
    if user.is_superuser or user.is_staff:
        return queryset

    return queryset.filter(
        Q(owner=user) |
        Q(stores__owner=user) |
        Q(stores__staff=user) |
        Q(company_profile__store__owner=user) |
        Q(company_profile__store__staff=user)
    ).distinct()


def _accessible_stores(user, accounts_qs=None):
    """Stores visible to current user."""
    queryset = Store.objects.filter(is_active=True)
    if user.is_superuser or user.is_staff:
        return queryset

    filters = Q(owner=user) | Q(staff=user)
    if accounts_qs is not None:
        filters |= Q(whatsapp_account_id__in=accounts_qs.values_list('id', flat=True))

    return queryset.filter(filters).distinct()


def _filter_store_queryset(queryset, store_param: Optional[str]):
    if not store_param:
        return queryset

    try:
        store_uuid = uuid.UUID(str(store_param))
        return queryset.filter(id=store_uuid)
    except (ValueError, TypeError, AttributeError):
        return queryset.filter(slug=store_param)


def _resolve_account_scope(user, account_id: Optional[str]):
    accounts_qs = _accessible_accounts(user)
    if not account_id:
        return accounts_qs, None

    try:
        account_uuid = uuid.UUID(str(account_id))
    except (ValueError, TypeError):
        return accounts_qs.none(), Response(
            {'detail': 'Invalid account_id.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    scoped = accounts_qs.filter(id=account_uuid)
    if scoped.exists():
        return scoped, None

    if WhatsAppAccount.objects.filter(id=account_uuid).exists():
        return accounts_qs.none(), Response(
            {'detail': 'Forbidden.'},
            status=status.HTTP_403_FORBIDDEN
        )

    return accounts_qs.none(), Response(
        {'detail': 'Account not found.'},
        status=status.HTTP_404_NOT_FOUND
    )


def _resolve_store_scope(user, store_param: Optional[str], accounts_qs=None):
    if accounts_qs is None:
        accounts_qs = _accessible_accounts(user)

    stores_qs = _accessible_stores(user, accounts_qs=accounts_qs)
    scoped = _filter_store_queryset(stores_qs, store_param)

    if not store_param:
        return scoped, None

    if scoped.exists():
        return scoped, None

    if _filter_store_queryset(Store.objects.all(), store_param).exists():
        return stores_qs.none(), Response(
            {'detail': 'Forbidden.'},
            status=status.HTTP_403_FORBIDDEN
        )

    return stores_qs.none(), Response(
        {'detail': 'Store not found.'},
        status=status.HTTP_404_NOT_FOUND
    )


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
        accounts_qs, account_error = _resolve_account_scope(request.user, account_id)
        if account_error:
            return account_error
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        account_ids = list(accounts_qs.values_list('id', flat=True))
        
        messages_qs = Message.objects.filter(account_id__in=account_ids)
        conversations_qs = Conversation.objects.filter(account_id__in=account_ids)
        store_param = request.query_params.get('store')
        stores_qs, store_error = _resolve_store_scope(request.user, store_param, accounts_qs=accounts_qs)
        if store_error:
            return store_error

        orders_qs = StoreOrder.objects.filter(is_active=True, store__in=stores_qs)
        
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

        # Agent metrics (replaces Langflow)
        agent_messages_qs = AgentMessage.objects.filter(
            conversation__agent__accounts__id__in=account_ids
        ).distinct()
        
        agent_interactions_today = agent_messages_qs.filter(
            created_at__gte=today_start,
            role='assistant'
        ).count()
        
        agent_avg_duration = agent_messages_qs.filter(
            created_at__gte=today_start,
            response_time_ms__isnull=False
        ).aggregate(avg=Avg('response_time_ms'))['avg'] or 0

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
            'agents': {
                'interactions_today': agent_interactions_today,
                'avg_duration_ms': round(agent_avg_duration, 2),
            },
            'timestamp': now.isoformat(),
        })


class DashboardProjectHealthView(APIView):
    """Project-wide operational health and KPI snapshot."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Project health dashboard",
        description="Get consolidated operational, API, commerce, messaging and automation health metrics.",
        responses={200: dict}
    )
    def get(self, request):
        account_id = request.query_params.get('account_id')
        accounts_qs, account_error = _resolve_account_scope(request.user, account_id)
        if account_error:
            return account_error

        store_param = request.query_params.get('store')
        stores_qs, store_error = _resolve_store_scope(request.user, store_param, accounts_qs=accounts_qs)
        if store_error:
            return store_error

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = now - timedelta(hours=24)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)

        account_ids = list(accounts_qs.values_list('id', flat=True))
        store_ids = list(stores_qs.values_list('id', flat=True))

        orders_qs = StoreOrder.objects.filter(is_active=True, store_id__in=store_ids)
        messages_qs = Message.objects.filter(account_id__in=account_ids)
        conversations_qs = Conversation.objects.filter(account_id__in=account_ids)
        products_qs = StoreProduct.objects.filter(store_id__in=store_ids)

        paid_orders_qs = orders_qs.filter(payment_status=StoreOrder.PaymentStatus.PAID)
        orders_today = orders_qs.filter(created_at__gte=today_start).count()
        orders_24h = orders_qs.filter(created_at__gte=day_start).count()
        orders_week = orders_qs.filter(created_at__gte=week_start).count()
        revenue_today = paid_orders_qs.filter(paid_at__gte=today_start).aggregate(total=Sum('total'))['total'] or 0
        revenue_month = paid_orders_qs.filter(paid_at__gte=month_start).aggregate(total=Sum('total'))['total'] or 0
        avg_ticket = paid_orders_qs.filter(paid_at__gte=month_start).aggregate(avg=Avg('total'))['avg'] or 0

        action_statuses = [
            StoreOrder.OrderStatus.PENDING,
            StoreOrder.OrderStatus.CONFIRMED,
            StoreOrder.OrderStatus.PROCESSING,
            StoreOrder.OrderStatus.PREPARING,
            StoreOrder.OrderStatus.READY,
        ]
        pending_orders = orders_qs.filter(status__in=action_statuses).count()
        payment_pending = orders_qs.filter(payment_status__in=[
            StoreOrder.PaymentStatus.PENDING,
            StoreOrder.PaymentStatus.PROCESSING,
        ]).count()
        cancelled_7d = orders_qs.filter(
            status__in=[StoreOrder.OrderStatus.CANCELLED, StoreOrder.OrderStatus.FAILED],
            created_at__gte=week_start,
        ).count()

        messages_24h = messages_qs.filter(created_at__gte=day_start).count()
        inbound_24h = messages_qs.filter(direction=Message.MessageDirection.INBOUND, created_at__gte=day_start).count()
        outbound_24h = messages_qs.filter(direction=Message.MessageDirection.OUTBOUND, created_at__gte=day_start).count()
        failed_messages_24h = messages_qs.filter(status=Message.MessageStatus.FAILED, created_at__gte=day_start).count()
        open_conversations = conversations_qs.filter(status__in=[
            Conversation.ConversationStatus.OPEN,
            Conversation.ConversationStatus.PENDING,
        ]).count()
        human_conversations = conversations_qs.filter(
            mode=Conversation.ConversationMode.HUMAN,
            status__in=[Conversation.ConversationStatus.OPEN, Conversation.ConversationStatus.PENDING],
        ).count()

        low_stock = products_qs.filter(
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=True,
            stock_quantity__lte=F('low_stock_threshold'),
        ).count()
        out_of_stock = products_qs.filter(
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=True,
            stock_quantity__lte=0,
            allow_backorder=False,
        ).count()

        from apps.automation.models import CompanyProfile
        from apps.automation.services.pipeline_health import get_pipeline_stats, health_check
        from apps.webhooks.models import WebhookEvent as CentralWebhookEvent

        profiles_qs = CompanyProfile.objects.filter(store_id__in=store_ids)
        ai_enabled_profiles = profiles_qs.filter(use_ai_agent=True, default_agent__isnull=False).count()
        active_agents = Agent.objects.filter(
            is_active=True,
            status=Agent.AgentStatus.ACTIVE,
        ).filter(
            Q(accounts__id__in=account_ids) | Q(company_profiles__store_id__in=store_ids)
        ).distinct().count()
        agent_messages_24h = AgentMessage.objects.filter(
            conversation__agent__is_active=True,
            created_at__gte=day_start,
        ).filter(
            Q(conversation__agent__accounts__id__in=account_ids) |
            Q(conversation__agent__company_profiles__store_id__in=store_ids)
        ).distinct().count()

        pipeline = get_pipeline_stats(hours=24)
        api_health = health_check()

        central_webhooks_24h = CentralWebhookEvent.objects.filter(created_at__gte=day_start)
        if store_ids:
            central_webhooks_24h = central_webhooks_24h.filter(Q(store_id__in=store_ids) | Q(store__isnull=True))

        whatsapp_webhooks_24h = WebhookEvent.objects.filter(created_at__gte=day_start, account_id__in=account_ids)
        webhook_failed_24h = (
            central_webhooks_24h.filter(status=CentralWebhookEvent.Status.FAILED).count()
            + whatsapp_webhooks_24h.filter(processing_status=WebhookEvent.ProcessingStatus.FAILED).count()
        )
        webhook_pending = (
            central_webhooks_24h.filter(status__in=[
                CentralWebhookEvent.Status.PENDING,
                CentralWebhookEvent.Status.PROCESSING,
            ]).count()
            + whatsapp_webhooks_24h.filter(processing_status__in=[
                WebhookEvent.ProcessingStatus.PENDING,
                WebhookEvent.ProcessingStatus.PROCESSING,
            ]).count()
        )

        issues = []
        if api_health.get('status') != 'ok':
            issues.append({
                'level': 'warning',
                'area': 'api',
                'title': 'API com status degradado',
                'detail': api_health.get('summary') or 'Verifique os checks de infraestrutura.',
            })
        if pending_orders:
            issues.append({
                'level': 'warning',
                'area': 'orders',
                'title': f'{pending_orders} pedidos precisam de ação',
                'detail': 'Pedidos pendentes, confirmados, em preparo ou prontos.',
            })
        if payment_pending:
            issues.append({
                'level': 'warning',
                'area': 'payments',
                'title': f'{payment_pending} pagamentos pendentes',
                'detail': 'Pedidos aguardando pagamento ou processamento.',
            })
        if failed_messages_24h:
            issues.append({
                'level': 'critical',
                'area': 'messages',
                'title': f'{failed_messages_24h} mensagens falharam em 24h',
                'detail': 'Falhas de envio ou status no WhatsApp.',
            })
        if webhook_failed_24h:
            issues.append({
                'level': 'critical',
                'area': 'webhooks',
                'title': f'{webhook_failed_24h} webhooks falharam em 24h',
                'detail': 'Eventos externos podem não ter sido processados.',
            })
        if low_stock:
            issues.append({
                'level': 'warning',
                'area': 'catalog',
                'title': f'{low_stock} produtos com estoque baixo',
                'detail': 'Produtos ativos abaixo do limite configurado.',
            })

        status_value = 'ok'
        if any(issue['level'] == 'critical' for issue in issues):
            status_value = 'critical'
        elif issues or api_health.get('status') == 'degraded':
            status_value = 'attention'

        return Response({
            'status': status_value,
            'generated_at': now.isoformat(),
            'scope': {
                'stores': stores_qs.count(),
                'accounts': accounts_qs.count(),
                'store_filter': store_param,
                'account_filter': account_id,
            },
            'api': {
                'status': api_health.get('status', 'unknown'),
                'checks': api_health.get('checks', {}),
                'summary': api_health.get('summary', ''),
            },
            'commerce': {
                'orders_today': orders_today,
                'orders_24h': orders_24h,
                'orders_7d': orders_week,
                'pending_orders': pending_orders,
                'payment_pending': payment_pending,
                'cancelled_7d': cancelled_7d,
                'revenue_today': float(revenue_today),
                'revenue_month': float(revenue_month),
                'avg_ticket_month': float(avg_ticket),
            },
            'catalog': {
                'active_products': products_qs.filter(status=StoreProduct.ProductStatus.ACTIVE).count(),
                'low_stock_products': low_stock,
                'out_of_stock_products': out_of_stock,
            },
            'messaging': {
                'messages_24h': messages_24h,
                'inbound_24h': inbound_24h,
                'outbound_24h': outbound_24h,
                'failed_24h': failed_messages_24h,
                'open_conversations': open_conversations,
                'human_conversations': human_conversations,
            },
            'automation': {
                'ai_enabled_profiles': ai_enabled_profiles,
                'active_agents': active_agents,
                'agent_messages_24h': agent_messages_24h,
                'pipeline': pipeline,
            },
            'webhooks': {
                'received_24h': central_webhooks_24h.count() + whatsapp_webhooks_24h.count(),
                'failed_24h': webhook_failed_24h,
                'pending': webhook_pending,
            },
            'issues': issues[:10],
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

        stores_qs, store_error = _resolve_store_scope(request.user, store_param)
        if store_error:
            return store_error

        store = stores_qs.first()
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
        try:
            limit = max(1, min(int(request.query_params.get('limit', 20)), 200))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Invalid limit.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        accounts_qs, account_error = _resolve_account_scope(request.user, account_id)
        if account_error:
            return account_error
        
        account_ids = list(accounts_qs.values_list('id', flat=True))

        store_param = request.query_params.get('store')
        stores_qs, store_error = _resolve_store_scope(request.user, store_param, accounts_qs=accounts_qs)
        if store_error:
            return store_error

        orders_qs = StoreOrder.objects.filter(is_active=True, store__in=stores_qs)

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
        try:
            days = max(1, min(int(request.query_params.get('days', 7)), 90))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Invalid days parameter.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        accounts_qs, account_error = _resolve_account_scope(request.user, account_id)
        if account_error:
            return account_error
        
        account_ids = list(accounts_qs.values_list('id', flat=True))
        store_param = request.query_params.get('store')
        stores_qs, store_error = _resolve_store_scope(request.user, store_param, accounts_qs=accounts_qs)
        if store_error:
            return store_error

        orders_qs = StoreOrder.objects.filter(is_active=True, store__in=stores_qs)
        
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
