"""
Intent and automation analytics API views.

These endpoints now use persisted logs (IntentLog/AutomationLog) instead of stubs.
"""
import csv
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

from django.db.models import Count, Avg, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.agents.models import Agent
from apps.automation.models import CompanyProfile, IntentLog, AutomationLog, CustomerSession
from apps.core.permissions import accessible_whatsapp_account_ids
from apps.whatsapp.intents.detector import IntentType

logger = logging.getLogger(__name__)


def _parse_date_range(request, default_days: int = 7) -> Tuple[datetime, datetime]:
    """
    Parse start_date/end_date query params.
    Expected format: YYYY-MM-DD
    """
    end_date = timezone.now()
    start_date = end_date - timedelta(days=default_days)

    start_date_str = request.query_params.get('start_date')
    end_date_str = request.query_params.get('end_date')

    if start_date_str:
        start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
    if end_date_str:
        end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d')) + timedelta(days=1)

    return start_date, end_date


def _accessible_companies(user):
    """Return company profiles accessible by current user."""
    if user.is_superuser or user.is_staff:
        return CompanyProfile.objects.all()

    account_ids = accessible_whatsapp_account_ids(user)
    return CompanyProfile.objects.filter(account_id__in=account_ids).distinct()


def _serialize_intent_log(log: IntentLog) -> Dict[str, Any]:
    return {
        'id': str(log.id),
        'created_at': log.created_at.isoformat(),
        'company_id': str(log.company_id),
        'conversation_id': str(log.conversation_id) if log.conversation_id else None,
        'message_id': str(log.message_id) if log.message_id else None,
        'phone_number': log.phone_number,
        'message_text': log.message_text,
        'intent_type': log.intent_type,
        'method': log.method,
        'confidence': float(log.confidence),
        'handler_used': log.handler_used,
        'response_type': log.response_type,
        'processing_time_ms': int(log.processing_time_ms),
        'entities': log.entities or {},
        'metadata': log.metadata or {},
    }


class IntentStatsViewSet(viewsets.ViewSet):
    """
    ViewSet for aggregated intent detection metrics.

    Endpoint:
    - GET /api/v1/whatsapp/intents/stats/
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        start_date, end_date = _parse_date_range(request)
        companies = _accessible_companies(request.user)

        company_id = request.query_params.get('company_id')
        if company_id:
            companies = companies.filter(id=company_id)

        logs = IntentLog.objects.filter(
            company__in=companies,
            created_at__gte=start_date,
            created_at__lt=end_date,
        )

        by_type = dict(
            logs.values('intent_type')
            .annotate(count=Count('id'))
            .values_list('intent_type', 'count')
        )
        by_method = dict(
            logs.values('method')
            .annotate(count=Count('id'))
            .values_list('method', 'count')
        )

        # Keep all known intents present in response shape for frontend stability.
        full_by_type = {intent.value: int(by_type.get(intent.value, 0)) for intent in IntentType}

        avg_response_time = logs.aggregate(avg=Avg('processing_time_ms'))['avg'] or 0
        top_intents = (
            logs.values('intent_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        return Response({
            'total_detected': logs.count(),
            'by_type': full_by_type,
            'by_method': {
                'regex': int(by_method.get('regex', 0)),
                'llm': int(by_method.get('llm', 0)),
                'none': int(by_method.get('none', 0)),
            },
            'avg_response_time_ms': round(float(avg_response_time), 2),
            'top_intents': list(top_intents),
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            }
        })


class IntentLogViewSet(viewsets.ViewSet):
    """
    ViewSet for intent log browsing.

    Endpoints:
    - GET /api/v1/whatsapp/intents/logs/
    - GET /api/v1/whatsapp/intents/logs/:id/
    - GET /api/v1/whatsapp/intents/logs/export/?format=json|csv
    """
    permission_classes = [IsAuthenticated]

    def _base_queryset(self, request):
        companies = _accessible_companies(request.user)

        company_id = request.query_params.get('company_id')
        if company_id:
            companies = companies.filter(id=company_id)

        qs = IntentLog.objects.filter(company__in=companies).select_related('company', 'conversation', 'message')

        intent_type = request.query_params.get('intent_type')
        if intent_type:
            qs = qs.filter(intent_type=intent_type)

        method = request.query_params.get('method')
        if method:
            qs = qs.filter(method=method)

        phone_number = request.query_params.get('phone_number')
        if phone_number:
            qs = qs.filter(phone_number__icontains=phone_number)

        start_date, end_date = _parse_date_range(request)
        qs = qs.filter(created_at__gte=start_date, created_at__lt=end_date)

        return qs.order_by('-created_at')

    def list(self, request):
        qs = self._base_queryset(request)

        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        total = qs.count()
        logs = qs[offset:offset + limit]
        results = [_serialize_intent_log(log) for log in logs]

        next_offset = offset + limit
        prev_offset = max(0, offset - limit)

        return Response({
            'count': total,
            'next': next_offset if next_offset < total else None,
            'previous': prev_offset if offset > 0 else None,
            'results': results,
        })

    def retrieve(self, request, pk=None):
        companies = _accessible_companies(request.user)
        log = get_object_or_404(IntentLog, id=pk, company__in=companies)
        return Response(_serialize_intent_log(log))

    @action(detail=False, methods=['get'])
    def export(self, request):
        fmt = (request.query_params.get('format') or 'json').lower()
        qs = self._base_queryset(request)
        logs = list(qs[:5000])

        if fmt == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="intent_logs.csv"'

            writer = csv.writer(response)
            writer.writerow([
                'id', 'created_at', 'company_id', 'phone_number', 'intent_type',
                'method', 'confidence', 'handler_used', 'response_type', 'processing_time_ms'
            ])
            for log in logs:
                writer.writerow([
                    str(log.id),
                    log.created_at.isoformat(),
                    str(log.company_id),
                    log.phone_number,
                    log.intent_type,
                    log.method,
                    float(log.confidence),
                    log.handler_used,
                    log.response_type,
                    int(log.processing_time_ms),
                ])
            return response

        return Response({
            'count': len(logs),
            'results': [_serialize_intent_log(log) for log in logs],
        })


class AutomationDashboardViewSet(viewsets.ViewSet):
    """
    ViewSet for automation dashboard metrics.

    Endpoint:
    - GET /api/v1/whatsapp/automation/dashboard/stats/
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        start_date, end_date = _parse_date_range(request)
        companies = _accessible_companies(request.user)

        company_id = request.query_params.get('company_id')
        if company_id:
            companies = companies.filter(id=company_id)

        logs = AutomationLog.objects.filter(
            company__in=companies,
            created_at__gte=start_date,
            created_at__lt=end_date,
        )

        sessions = CustomerSession.objects.filter(
            company__in=companies,
            created_at__gte=start_date,
            created_at__lt=end_date,
        )

        total_messages_sent = logs.filter(
            action_type=AutomationLog.ActionType.MESSAGE_SENT
        ).count()
        total_automations_triggered = logs.exclude(
            action_type=AutomationLog.ActionType.ERROR
        ).count()

        converted_sessions = sessions.filter(
            status__in=[
                CustomerSession.SessionStatus.PAYMENT_CONFIRMED,
                CustomerSession.SessionStatus.ORDER_PLACED,
                CustomerSession.SessionStatus.COMPLETED,
            ]
        )
        conversion_rate = (
            (converted_sessions.count() / sessions.count()) * 100
            if sessions.exists() else 0.0
        )
        revenue_from_automations = converted_sessions.aggregate(
            total=Sum('order__total')
        )['total'] or 0

        by_event_type = dict(
            logs.values('event_type')
            .annotate(count=Count('id'))
            .values_list('event_type', 'count')
        )

        abandoned_carts = sessions.filter(
            status=CustomerSession.SessionStatus.CART_ABANDONED
        ).count()
        cart_reminders_sent = logs.filter(
            action_type=AutomationLog.ActionType.NOTIFICATION_SENT,
        ).filter(
            Q(event_type__icontains='cart') | Q(description__icontains='cart')
        ).count()
        recovered_sessions = converted_sessions.exclude(cart_data={})
        recovered_count = recovered_sessions.count()
        recovery_rate = (recovered_count / abandoned_carts * 100) if abandoned_carts else 0.0
        revenue_recovered = recovered_sessions.aggregate(total=Sum('order__total'))['total'] or 0

        pending_payments = sessions.filter(
            status=CustomerSession.SessionStatus.PAYMENT_PENDING
        ).count()
        payment_reminders_sent = logs.filter(
            action_type=AutomationLog.ActionType.NOTIFICATION_SENT,
        ).filter(
            Q(event_type__icontains='payment') | Q(description__icontains='pagamento')
        ).count()
        paid_after_reminder = sessions.filter(
            status__in=[
                CustomerSession.SessionStatus.PAYMENT_CONFIRMED,
                CustomerSession.SessionStatus.ORDER_PLACED,
                CustomerSession.SessionStatus.COMPLETED,
            ]
        ).count()
        payment_conversion_rate = (
            (paid_after_reminder / payment_reminders_sent) * 100
            if payment_reminders_sent else 0.0
        )

        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            },
            'summary': {
                'total_messages_sent': total_messages_sent,
                'total_automations_triggered': total_automations_triggered,
                'conversion_rate': round(conversion_rate, 2),
                'revenue_from_automations': float(revenue_from_automations),
            },
            'by_event_type': by_event_type,
            'cart_recovery': {
                'abandoned_carts': abandoned_carts,
                'reminders_sent': cart_reminders_sent,
                'recovered': recovered_count,
                'recovery_rate': round(recovery_rate, 2),
                'revenue_recovered': float(revenue_recovered),
            },
            'payment_reminders': {
                'pending_payments': pending_payments,
                'reminders_sent': payment_reminders_sent,
                'paid_after_reminder': paid_after_reminder,
                'conversion_rate': round(payment_conversion_rate, 2),
            },
        })


class AutomationSettingsViewSet(viewsets.ViewSet):
    """
    ViewSet for automation settings bound to CompanyProfile.

    Endpoints:
    - GET /api/v1/whatsapp/automation/settings/
    - PATCH /api/v1/whatsapp/automation/settings/
    """
    permission_classes = [IsAuthenticated]

    def _get_target_company(self, request):
        companies = _accessible_companies(request.user)
        company_id = request.query_params.get('company_id') or request.data.get('company_id')

        if company_id:
            return get_object_or_404(companies, id=company_id)

        company = companies.order_by('created_at').first()
        if not company:
            return None
        return company

    def _serialize_settings(self, company: CompanyProfile) -> Dict[str, Any]:
        return {
            'company_id': str(company.id),
            'cart_recovery': {
                'enabled': bool(company.abandoned_cart_notification),
                'delay_minutes': int(company.abandoned_cart_delay_minutes),
            },
            'payment_reminders': {
                'enabled': bool(company.pix_notification_enabled),
                'payment_confirmation_enabled': bool(company.payment_confirmation_enabled),
            },
            'order_notifications': {
                'enabled': bool(company.order_status_notification_enabled),
                'delivery_notifications_enabled': bool(company.delivery_notification_enabled),
            },
            'ai_agent': {
                'enabled': bool(company.use_ai_agent),
                'default_agent_id': str(company.default_agent_id) if company.default_agent_id else None,
            },
        }

    def list(self, request):
        company = self._get_target_company(request)
        if not company:
            return Response(
                {'detail': 'No accessible company profile found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(self._serialize_settings(company))

    def partial_update(self, request):
        company = self._get_target_company(request)
        if not company:
            return Response(
                {'detail': 'No accessible company profile found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        data = request.data or {}
        updated_fields = []

        cart_recovery = data.get('cart_recovery', {})
        if 'enabled' in cart_recovery:
            company.abandoned_cart_notification = bool(cart_recovery['enabled'])
            updated_fields.append('abandoned_cart_notification')
        if 'delay_minutes' in cart_recovery:
            delay = max(1, int(cart_recovery['delay_minutes']))
            company.abandoned_cart_delay_minutes = delay
            updated_fields.append('abandoned_cart_delay_minutes')

        payment_reminders = data.get('payment_reminders', {})
        if 'enabled' in payment_reminders:
            company.pix_notification_enabled = bool(payment_reminders['enabled'])
            updated_fields.append('pix_notification_enabled')
        if 'payment_confirmation_enabled' in payment_reminders:
            company.payment_confirmation_enabled = bool(payment_reminders['payment_confirmation_enabled'])
            updated_fields.append('payment_confirmation_enabled')

        order_notifications = data.get('order_notifications', {})
        if 'enabled' in order_notifications:
            company.order_status_notification_enabled = bool(order_notifications['enabled'])
            updated_fields.append('order_status_notification_enabled')
        if 'delivery_notifications_enabled' in order_notifications:
            company.delivery_notification_enabled = bool(order_notifications['delivery_notifications_enabled'])
            updated_fields.append('delivery_notification_enabled')

        ai_agent = data.get('ai_agent', {})
        if 'enabled' in ai_agent:
            company.use_ai_agent = bool(ai_agent['enabled'])
            updated_fields.append('use_ai_agent')
        if 'default_agent_id' in ai_agent:
            default_agent_id = ai_agent['default_agent_id']
            if default_agent_id:
                account_id = company.account_id
                candidate_agents = Agent.objects.filter(status='active')
                if account_id:
                    candidate_agents = candidate_agents.filter(
                        Q(accounts__id=account_id) |
                        Q(whatsapp_accounts__id=account_id) |
                        Q(company_profiles=company)
                    ).distinct()
                agent = get_object_or_404(candidate_agents, id=default_agent_id)
                company.default_agent = agent
            else:
                company.default_agent = None
            updated_fields.append('default_agent')

        if updated_fields:
            company.save(update_fields=list(set(updated_fields + ['updated_at'])))
            if 'use_ai_agent' in updated_fields or 'default_agent' in updated_fields:
                company.sync_ai_settings_to_account()

        return Response(self._serialize_settings(company))
