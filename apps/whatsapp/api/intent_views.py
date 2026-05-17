"""
Intent Detection API Views

Endpoints para estatísticas e logs de detecção de intenções.
"""
from datetime import datetime, timedelta
from typing import Any, Dict

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum
from django.db import connection

from apps.whatsapp.intents.detector import IntentType
from apps.whatsapp.models.intent_models import IntentLog, IntentDailyStats


class IntentStatsViewSet(viewsets.ViewSet):
    """
    ViewSet para estatísticas de detecção de intenções.
    
    endpoints:
    - GET /api/whatsapp/intents/stats/
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Retorna estatísticas agregadas de intenções.
        
        Query params:
        - start_date: Data inicial (YYYY-MM-DD)
        - end_date: Data final (YYYY-MM-DD)
        - account_id: ID da conta (opcional)
        """
        # Parâmetros de data
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        account_id = request.query_params.get('account_id')
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # Query base
        queryset = IntentLog.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Estatísticas agregadas
        total_detected = queryset.count()
        
        # Por método
        by_method = {
            'regex': queryset.filter(method='regex').count(),
            'llm': queryset.filter(method='llm').count(),
        }
        
        # Por tipo
        by_type = {}
        for intent in IntentType:
            count = queryset.filter(intent_type=intent.value).count()
            by_type[intent.value] = count
        
        # Tempo médio de resposta
        avg_time = queryset.aggregate(avg_time=Avg('processing_time_ms'))['avg_time'] or 0
        
        # Top intenções
        top_intents = list(
            queryset.values('intent_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )
        
        stats = {
            'total_detected': total_detected,
            'by_type': by_type,
            'by_method': by_method,
            'avg_response_time_ms': round(avg_time, 2),
            'top_intents': [
                {'intent': item['intent_type'], 'count': item['count']}
                for item in top_intents
            ],
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            }
        }
        
        return Response(stats)


class IntentLogViewSet(viewsets.ViewSet):
    """
    ViewSet para logs de detecção de intenções.
    
    endpoints:
    - GET /api/whatsapp/intents/logs/
    - GET /api/whatsapp/intents/logs/:id/
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Lista logs de intenções com filtros.
        
        Query params:
        - limit: Limite de resultados (padrão: 20)
        - offset: Offset para paginação
        - intent_type: Filtrar por tipo de intenção
        - method: Filtrar por método (regex/llm)
        - start_date: Data inicial
        - end_date: Data final
        - account_id: ID da conta
        - phone_number: Filtrar por telefone
        """
        # Parâmetros
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        intent_type = request.query_params.get('intent_type')
        method = request.query_params.get('method')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        account_id = request.query_params.get('account_id')
        phone_number = request.query_params.get('phone_number')
        
        # Query base
        queryset = IntentLog.objects.all()
        
        # Filtros
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        if intent_type:
            queryset = queryset.filter(intent_type=intent_type)
        if method:
            queryset = queryset.filter(method=method)
        if phone_number:
            queryset = queryset.filter(phone_number__contains=phone_number)
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Ordenação e paginação
        total_count = queryset.count()
        queryset = queryset.order_by('-created_at')[offset:offset + limit]
        
        # Serialização manual
        results = []
        for log in queryset:
            results.append({
                'id': str(log.id),
                'message_id': str(log.message_id) if log.message else None,
                'conversation_id': str(log.conversation_id) if log.conversation else None,
                'phone_number': log.phone_number,
                'message_text': log.message_text,
                'intent_type': log.intent_type,
                'method': log.method,
                'confidence': log.confidence,
                'handler_used': log.handler_used,
                'response_text': log.response_text,
                'response_type': log.response_type,
                'processing_time_ms': log.processing_time_ms,
                'created_at': log.created_at.isoformat(),
            })
        
        return Response({
            'count': total_count,
            'next': offset + limit < total_count,
            'previous': offset > 0,
            'results': results,
        })
    
    def retrieve(self, request, pk=None):
        """Retorna um log específico."""
        try:
            log = IntentLog.objects.get(id=pk)
            return Response({
                'id': str(log.id),
                'message_id': str(log.message_id) if log.message else None,
                'conversation_id': str(log.conversation_id) if log.conversation else None,
                'phone_number': log.phone_number,
                'message_text': log.message_text,
                'intent_type': log.intent_type,
                'method': log.method,
                'confidence': log.confidence,
                'handler_used': log.handler_used,
                'response_text': log.response_text,
                'response_type': log.response_type,
                'processing_time_ms': log.processing_time_ms,
                'context': log.context,
                'entities': log.entities,
                'created_at': log.created_at.isoformat(),
            })
        except IntentLog.DoesNotExist:
            return Response(
                {'detail': 'Log não encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Exporta logs para CSV ou JSON.
        
        Query params:
        - format: 'csv' ou 'json' (padrão: json)
        - start_date: Data inicial
        - end_date: Data final
        """
        export_format = request.query_params.get('format', 'json')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        account_id = request.query_params.get('account_id')
        
        # Query base
        queryset = IntentLog.objects.all()
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            queryset = queryset.filter(created_at__lte=end_date)
        
        queryset = queryset.order_by('-created_at')
        
        if export_format == 'csv':
            import csv
            import io
            from django.http import HttpResponse
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                'ID', 'Data', 'Telefone', 'Mensagem', 'Intenção',
                'Método', 'Confiança', 'Handler', 'Tempo (ms)'
            ])
            
            for log in queryset:
                writer.writerow([
                    str(log.id),
                    log.created_at.isoformat(),
                    log.phone_number,
                    log.message_text[:100],
                    log.intent_type,
                    log.method,
                    log.confidence,
                    log.handler_used,
                    log.processing_time_ms,
                ])
            
            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="intent_logs.csv"'
            return response
        
        # JSON
        results = []
        for log in queryset:
            results.append({
                'id': str(log.id),
                'created_at': log.created_at.isoformat(),
                'phone_number': log.phone_number,
                'message_text': log.message_text,
                'intent_type': log.intent_type,
                'method': log.method,
                'confidence': log.confidence,
                'handler_used': log.handler_used,
                'response_text': log.response_text,
                'processing_time_ms': log.processing_time_ms,
            })
        
        return Response(results)


class AutomationDashboardViewSet(viewsets.ViewSet):
    """
    ViewSet para dashboard de automações.
    
    endpoints:
    - GET /api/automation/dashboard/stats/
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Retorna estatísticas do dashboard de automações.
        
        Query params:
        - start_date: Data inicial
        - end_date: Data final
        - account_id: ID da conta
        """
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        account_id = request.query_params.get('account_id')
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        # Query base de logs
        queryset = IntentLog.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        # Estatísticas por tipo de evento (baseado nas intenções)
        by_event_type = {}
        for intent in IntentType:
            count = queryset.filter(intent_type=intent.value).count()
            if count > 0:
                by_event_type[intent.value] = count
        
        total_logs = queryset.count()
        automations_triggered = queryset.exclude(handler_used='').count()
        payment_confirmed_count = queryset.filter(intent_type='payment_confirmed').count()

        # Conversion rate: confirmações de pagamento / automações disparadas
        conversion_rate = (
            round(payment_confirmed_count / automations_triggered * 100, 2)
            if automations_triggered > 0 else 0.0
        )

        # Receita de automações: pedidos pagos de clientes que passaram por automação
        phones_in_automations = queryset.exclude(handler_used='').values_list(
            'phone_number', flat=True
        ).distinct()

        try:
            from apps.stores.models import StoreOrder
            revenue_qs = StoreOrder.objects.filter(
                customer_phone__in=phones_in_automations,
                payment_status='paid',
                created_at__gte=start_date,
                created_at__lte=end_date,
            )
            revenue_from_automations = float(
                revenue_qs.aggregate(total=Sum('total'))['total'] or 0
            )
        except Exception:
            revenue_from_automations = 0.0

        # Cart recovery: phones que tiveram cart_abandoned E depois payment_confirmed
        abandoned_phones = set(
            queryset.filter(intent_type='cart_abandoned').values_list('phone_number', flat=True)
        )
        recovered_phones = set(
            queryset.filter(intent_type='payment_confirmed').values_list('phone_number', flat=True)
        )
        abandoned_carts = len(abandoned_phones)
        recovered_count = len(abandoned_phones & recovered_phones)
        recovery_rate = (
            round(recovered_count / abandoned_carts * 100, 2) if abandoned_carts > 0 else 0.0
        )

        # Receita recuperada de carrinhos
        try:
            recovered_revenue = float(
                StoreOrder.objects.filter(
                    customer_phone__in=list(abandoned_phones & recovered_phones),
                    payment_status='paid',
                    created_at__gte=start_date,
                    created_at__lte=end_date,
                ).aggregate(total=Sum('total'))['total'] or 0
            )
        except Exception:
            recovered_revenue = 0.0

        # Payment reminders conversion
        pix_reminders_sent = queryset.filter(intent_type='pix_reminder').count()
        pix_phones_reminded = set(
            queryset.filter(intent_type='pix_reminder').values_list('phone_number', flat=True)
        )
        paid_after_reminder = queryset.filter(
            intent_type='payment_confirmed',
            phone_number__in=pix_phones_reminded,
        ).count()
        reminder_conversion = (
            round(paid_after_reminder / pix_reminders_sent * 100, 2)
            if pix_reminders_sent > 0 else 0.0
        )

        stats = {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            },
            'summary': {
                'total_messages_sent': total_logs,
                'total_automations_triggered': automations_triggered,
                'conversion_rate': conversion_rate,
                'revenue_from_automations': revenue_from_automations,
            },
            'by_event_type': by_event_type,
            'cart_recovery': {
                'abandoned_carts': abandoned_carts,
                'reminders_sent': queryset.filter(intent_type='cart_reminder').count(),
                'recovered': recovered_count,
                'recovery_rate': recovery_rate,
                'revenue_recovered': recovered_revenue,
            },
            'payment_reminders': {
                'pending_payments': queryset.filter(intent_type='pix_generated').count(),
                'reminders_sent': pix_reminders_sent,
                'paid_after_reminder': paid_after_reminder,
                'conversion_rate': reminder_conversion,
            },
        }

        return Response(stats)


class AutomationSettingsViewSet(viewsets.ViewSet):
    """
    ViewSet para configurações de automação.
    
    endpoints:
    - GET /api/automation/settings/
    - PATCH /api/automation/settings/
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Retorna configurações atuais."""
        # TODO: Implementar com modelo de configurações
        settings = {
            'cart_recovery': {
                'enabled': True,
                'reminder_30min': True,
                'reminder_2h': True,
                'reminder_24h': False,
                'discount_code': None,
            },
            'payment_reminders': {
                'enabled': True,
                'reminder_30min': True,
                'reminder_2h': True,
                'auto_cancel_after_24h': True,
            },
            'order_notifications': {
                'enabled': True,
                'on_confirmed': True,
                'on_preparing': True,
                'on_ready': True,
                'on_out_for_delivery': True,
                'on_delivered': True,
            },
            'feedback_request': {
                'enabled': True,
                'delay_minutes': 30,
            },
        }
        return Response(settings)
    
    def partial_update(self, request):
        """Atualiza configurações."""
        # TODO: Implementar atualização
        return Response(
            {'detail': 'Settings update not implemented yet.'},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
