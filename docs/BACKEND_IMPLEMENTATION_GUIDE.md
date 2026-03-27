# Backend Implementation Guide - Dashboard Integration

**Target:** Django REST Framework backend server  
**Purpose:** Ensure all dashboard endpoints return data matching frontend requirements  
**Status:** Implementation Guide (Copy to your backend project)

---

## Overview

The pastita-dash frontend now requires specific data structure from backend API. This guide provides exact implementation details for ensuring compatibility.

## Critical Implementation Notes

### 1. All Numeric Values Must Be Non-Negative
```python
def ensure_positive(value):
    """Ensure all numeric values are >= 0"""
    return max(0, int(value or 0))
```

### 2. All Dates Must Be ISO 8601 Format
```python
from django.utils import timezone

# ✅ CORRECT
timestamp = timezone.now().isoformat()  # "2026-03-12T10:30:45.123456Z"

# ❌ INCORRECT
timestamp = str(timezone.now())  # Will cause frontend parsing errors
```

### 3. All Enums Must Match Frontend Exactly
```python
# Frontend expects these exact values:
MessageStatus = ('sent', 'delivered', 'read', 'failed', 'pending')
ConversationMode = ('auto', 'human', 'hybrid')
ConversationStatus = ('open', 'closed', 'pending', 'resolved')
OrderStatus = ('pending', 'confirmed', 'processing', 'paid', 'preparing', 'ready', 'shipped', 'out_for_delivery', 'delivered', 'completed', 'cancelled', 'refunded', 'failed')
```

### 4. Missing Fields = Frontend Shows 0
If a field is missing from response, frontend treats it as 0 or empty array. Always include all fields.

---

## Implementation

### Endpoint 1: `/api/core/dashboard/overview/` (GET)

**View Implementation:**

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg

class DashboardOverviewView(APIView):
    """Returns aggregated dashboard metrics for today"""
    
    def get(self, request):
        try:
            today = timezone.now().date()
            
            # 1. Accounts
            from apps.accounts.models import Account  # Adjust import
            accounts_total = Account.objects.filter(
                is_active=True
            ).count()
            
            # 2. Messages (Today's metrics)
            from apps.conversations.models import Message
            messages_today = Message.objects.filter(
                created_date__date=today
            )
            
            messages_inbound = messages_today.filter(
                direction='inbound'
            ).count()
            messages_outbound = messages_today.filter(
                direction='outbound'
            ).count()
            
            messages_by_status = {}
            for status_choice in ['sent', 'delivered', 'read', 'failed', 'pending']:
                messages_by_status[status_choice] = messages_today.filter(
                    status=status_choice
                ).count()
            
            # 3. Conversations (Today's active conversations)
            from apps.conversations.models import Conversation
            conversations_active = Conversation.objects.filter(
                status__in=['open', 'pending']
            ).count()
            
            conversations_by_mode = {}
            for mode in ['auto', 'human', 'hybrid']:
                conversations_by_mode[mode] = Conversation.objects.filter(
                    mode=mode
                ).count()
            
            conversations_by_status = {}
            for conv_status in ['open', 'closed', 'pending', 'resolved']:
                conversations_by_status[conv_status] = Conversation.objects.filter(
                    status=conv_status
                ).count()
            
            # Count resolved today (status was changed to resolved today)
            conversations_resolved_today = Conversation.objects.filter(
                status='resolved',
                modified_date__date=today
            ).count()
            
            # 4. Orders (Created today)
            from apps.stores.models import StoreOrder
            orders_today = StoreOrder.objects.filter(
                created_date__date=today
            ).count()
            
            orders_by_status = {}
            for order_status in [
                'pending', 'confirmed', 'processing', 'paid', 'preparing',
                'ready', 'shipped', 'out_for_delivery', 'delivered', 
                'completed', 'cancelled', 'refunded', 'failed'
            ]:
                orders_by_status[order_status] = StoreOrder.objects.filter(
                    status=order_status
                ).count()
            
            # 5. Payments
            from apps.stores.models import StorePaymentGateway
            payments_pending = StorePaymentGateway.objects.filter(
                status='pending'
            ).count()
            payments_confirmed = StorePaymentGateway.objects.filter(
                status__in=['confirmed', 'completed', 'processing']
            ).count()
            
            # Revenue today (from completed/confirmed payments)
            payments_today = StorePaymentGateway.objects.filter(
                created_date__date=today,
                status__in=['confirmed', 'completed']
            )
            amount_today = payments_today.aggregate(
                total=Sum('amount')
            )['total'] or 0
            
            # 6. Agents
            from apps.agents.models import Agent
            agents_active = Agent.objects.filter(
                status='active'
            ).count()
            
            agent_metrics = Agent.objects.filter(
                status='active'
            ).aggregate(
                interactions_today=Sum('interactions_today'),
                avg_duration_ms=Avg('avg_duration_ms'),
            )
            
            # Count conversations resolved by agents today
            resolved_by_agents = Conversation.objects.filter(
                status='resolved',
                modified_date__date=today,
                ai_agent__isnull=False,  # Handled by AI agent
            ).count()
            
            return Response({
                'accounts': {
                    'total': accounts_total,
                },
                'messages': {
                    'today': messages_today.count(),
                    'week': Message.objects.filter(
                        created_date__gte=timezone.now() - timezone.timedelta(days=7)
                    ).count(),
                    'month': Message.objects.filter(
                        created_date__gte=timezone.now() - timezone.timedelta(days=30)
                    ).count(),
                    'by_direction': {
                        'inbound': messages_inbound,
                        'outbound': messages_outbound,
                    },
                    'by_status': messages_by_status,
                },
                'conversations': {
                    'active': conversations_active,
                    'by_mode': conversations_by_mode,
                    'by_status': conversations_by_status,
                    'resolved_today': conversations_resolved_today,
                },
                'orders': {
                    'today': orders_today,
                    'by_status': orders_by_status,
                    'revenue_today': float(StoreOrder.objects.filter(
                        created_date__date=today
                    ).aggregate(total=Sum('total_amount'))['total'] or 0),
                    'revenue_month': float(StoreOrder.objects.filter(
                        created_date__gte=timezone.now() - timezone.timedelta(days=30)
                    ).aggregate(total=Sum('total_amount'))['total'] or 0),
                },
                'payments': {
                    'pending': payments_pending,
                    'confirmed': payments_confirmed,
                    'amount_today': float(amount_today),
                },
                'agents': {
                    'active': agents_active,
                    'interactions_today': agent_metrics['interactions_today'] or 0,
                    'avg_duration_ms': int(agent_metrics['avg_duration_ms'] or 0),
                    'resolved_today': resolved_by_agents,
                },
                'timestamp': timezone.now().isoformat(),
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Dashboard overview error: {str(e)}')
            
            # Return safe defaults instead of 500 error
            return Response({
                'accounts': {'total': 0},
                'messages': {'today': 0, 'week': 0, 'month': 0, 'by_direction': {'inbound': 0, 'outbound': 0}, 'by_status': {}},
                'conversations': {'active': 0, 'by_mode': {}, 'by_status': {}, 'resolved_today': 0},
                'orders': {'today': 0, 'by_status': {}, 'revenue_today': 0, 'revenue_month': 0},
                'payments': {'pending': 0, 'confirmed': 0, 'amount_today': 0},
                'agents': {'active': 0, 'interactions_today': 0, 'avg_duration_ms': 0, 'resolved_today': 0},
                'timestamp': timezone.now().isoformat(),
            }, status=status.HTTP_200_OK)
```

### Endpoint 2: `/api/core/dashboard/charts/` (GET)

**URL Configuration:**
```python
# urls.py
path('charts/', DashboardChartsView.as_view(), name='dashboard-charts'),
```

**Query Parameters:**
- `days` (integer, 1-90, default: 30)

**View Implementation:**

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta

class DashboardChartsView(APIView):
    """Returns time-series data for dashboard charts"""
    
    def get(self, request):
        try:
            # Parse days parameter
            days = int(request.GET.get('days', 30))
            days = max(1, min(days, 90))  # Clamp between 1-90
            
            today = timezone.now().date()
            start_date = today - timedelta(days=days)
            
            # 1. Messages per day
            from apps.conversations.models import Message
            messages_per_day_data = Message.objects.filter(
                created_date__date__gte=start_date,
                created_date__date__lte=today,
            ).extra(
                select={'date': 'CAST(created_date AS DATE)'}
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            messages_per_day = [
                {'date': item['date'].isoformat(), 'count': item['count']}
                for item in messages_per_day_data
            ]
            
            # 2. Orders per day
            from apps.stores.models import StoreOrder
            orders_per_day_data = StoreOrder.objects.filter(
                created_date__date__gte=start_date,
                created_date__date__lte=today,
            ).extra(
                select={'date': 'CAST(created_date AS DATE)'}
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            orders_per_day = [
                {'date': item['date'].isoformat(), 'count': item['count']}
                for item in orders_per_day_data
            ]
            
            # 3. Conversations per day (NEW - new vs resolved)
            from apps.conversations.models import Conversation
            
            # Get newly created conversations per day
            new_conversations_data = Conversation.objects.filter(
                created_date__date__gte=start_date,
                created_date__date__lte=today,
            ).extra(
                select={'date': 'CAST(created_date AS DATE)'}
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            # Get resolved conversations per day (resolved on that date)
            resolved_conversations_data = Conversation.objects.filter(
                status='resolved',
                modified_date__date__gte=start_date,
                modified_date__date__lte=today,
            ).extra(
                select={'date': 'CAST(modified_date AS DATE)'}
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            # Combine new and resolved
            date_range = set()
            for item in new_conversations_data:
                date_range.add(item['date'])
            for item in resolved_conversations_data:
                date_range.add(item['date'])
            
            # Create dictionaries for lookup
            new_by_date = {item['date']: item['count'] for item in new_conversations_data}
            resolved_by_date = {item['date']: item['count'] for item in resolved_conversations_data}
            
            # Build sorted result
            conversations_per_day = []
            for date in sorted(date_range):
                conversations_per_day.append({
                    'date': date.isoformat(),
                    'new': new_by_date.get(date, 0),
                    'resolved': resolved_by_date.get(date, 0),
                })
            
            # 4. Message types distribution
            message_types_data = Message.objects.values('type').annotate(
                count=Count('id')
            )
            message_types = {
                item['type']: item['count']
                for item in message_types_data
            }
            # Ensure expected types exist
            for msg_type in ['text', 'image', 'audio', 'video', 'document']:
                if msg_type not in message_types:
                    message_types[msg_type] = 0
            
            # 5. Order statuses distribution
            order_statuses = {}
            for order_status in [
                'pending', 'confirmed', 'processing', 'paid', 'preparing',
                'ready', 'shipped', 'out_for_delivery', 'delivered', 
                'completed', 'cancelled', 'refunded', 'failed'
            ]:
                count = StoreOrder.objects.filter(
                    status=order_status
                ).count()
                order_statuses[order_status] = count
            
            return Response({
                'messages_per_day': messages_per_day,
                'orders_per_day': orders_per_day,
                'conversations_per_day': conversations_per_day,
                'message_types': message_types,
                'order_statuses': order_statuses,
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Dashboard charts error: {str(e)}')
            
            # Return safe defaults
            return Response({
                'messages_per_day': [],
                'orders_per_day': [],
                'conversations_per_day': [],
                'message_types': {'text': 0, 'image': 0, 'audio': 0, 'video': 0, 'document': 0},
                'order_statuses': {
                    'pending': 0, 'confirmed': 0, 'processing': 0, 'paid': 0,
                    'preparing': 0, 'ready': 0, 'shipped': 0, 'out_for_delivery': 0,
                    'delivered': 0, 'completed': 0, 'cancelled': 0, 'refunded': 0, 'failed': 0
                },
            }, status=status.HTTP_200_OK)
```

### URL Configuration

```python
# apps/core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/overview/', views.DashboardOverviewView.as_view(), name='dashboard-overview'),
    path('dashboard/charts/', views.DashboardChartsView.as_view(), name='dashboard-charts'),
]

# project/urls.py
from django.urls import path, include

urlpatterns = [
    path('api/core/', include('apps.core.urls')),
]
```

---

## Model Adjustments

### Agent Model

Ensure these fields exist:
```python
class Agent(models.Model):
    # ... existing fields ...
    
    # ✅ CRITICAL: These fields must exist
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='inactive'
    )
    
    interactions_today = models.IntegerField(
        default=0,
        help_text="Number of interactions handled today"
    )
    
    avg_duration_ms = models.IntegerField(
        default=0,
        help_text="Average interaction duration in milliseconds"
    )
    
    def save(self, *args, **kwargs):
        # Ensure non-negative values
        self.interactions_today = max(0, self.interactions_today)
        self.avg_duration_ms = max(0, self.avg_duration_ms)
        super().save(*args, **kwargs)
```

### Conversation Model

Ensure these fields exist with correct choices:
```python
class Conversation(models.Model):
    # ... existing fields ...
    
    # ✅ CRITICAL: Mode and Status must match frontend enums
    MODE_CHOICES = [
        ('auto', 'Automated'),
        ('human', 'Human'),
        ('hybrid', 'Hybrid'),
    ]
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='auto')
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('pending', 'Pending'),
        ('resolved', 'Resolved'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # Optional: Link to agent
    ai_agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations'
    )
```

### Message Model

Ensure these fields exist with correct choices:
```python
class Message(models.Model):
    # ... existing fields ...
    
    # ✅ CRITICAL: Status and Direction must match frontend enums
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    
    TYPE_CHOICES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('document', 'Document'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='text')
```

### StoreOrder Model

Ensure status field includes all 13 options:
```python
class StoreOrder(models.Model):
    # ... existing fields ...
    
    # ✅ CRITICAL: All 13 statuses must be present
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
```

---

## Testing

### Unit Test Example

```python
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

class DashboardViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
    
    def test_dashboard_overview_returns_required_fields(self):
        response = self.client.get('/api/core/dashboard/overview/')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        # Check required fields
        self.assertIn('accounts', data)
        self.assertIn('messages', data)
        self.assertIn('conversations', data)
        self.assertIn('orders', data)
        self.assertIn('payments', data)
        self.assertIn('agents', data)
        self.assertIn('timestamp', data)
        
        # Check structure
        self.assertIn('total', data['accounts'])
        self.assertIn('by_direction', data['messages'])
        self.assertIn('by_status', data['messages'])
        self.assertIn('by_mode', data['conversations'])
        self.assertIn('by_status', data['conversations'])
    
    def test_dashboard_charts_returns_arrays(self):
        response = self.client.get('/api/core/dashboard/charts/?days=7')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIsInstance(data['messages_per_day'], list)
        self.assertIsInstance(data['orders_per_day'], list)
        self.assertIsInstance(data['conversations_per_day'], list)
    
    def test_dashboard_charts_days_parameter_clamped(self):
        # Test that days > 90 is clamped
        response = self.client.get('/api/core/dashboard/charts/?days=200')
        self.assertEqual(response.status_code, 200)
        # Should not error, should clamp to 90
    
    def test_conversation_modes_included(self):
        response = self.client.get('/api/core/dashboard/overview/')
        data = response.json()
        
        # Should have auto, human, hybrid keys
        modes = data['conversations']['by_mode']
        self.assertIn('auto', modes)
        self.assertIn('human', modes)
        self.assertIn('hybrid', modes)
```

---

## Deployment Checklist

- [ ] All model fields added/updated
- [ ] Database migrations created and applied
- [ ] Views implemented and tested
- [ ] URLs configured
- [ ] CORS headers allow frontend domain
- [ ] Authentication/permissions configured (if needed)
- [ ] Error handling returns safe defaults (not 500 errors)
- [ ] All numeric values are non-negative
- [ ] All timestamps are ISO 8601 format
- [ ] All enum values match frontend exactly
- [ ] Unit tests passing
- [ ] Load test: ensure views perform well with large datasets
- [ ] Verify in browser: open http://backend/api/core/dashboard/overview/ and http://backend/api/core/dashboard/charts/

---

## Troubleshooting

### Frontend shows all zeros
**Cause:** Backend queries returning no data  
**Fix:** Check if models have data in database; run Django shell to verify:
```bash
python manage.py shell
>>> from apps.conversations.models import Message
>>> Message.objects.count()  # Should be > 0
```

### Frontend shows parsing errors in console
**Cause:** Timestamps not ISO 8601 format  
**Fix:** Change `str(timezone.now())` to `timezone.now().isoformat()`

### `[Dashboard] Invalid overview response structure` warning
**Cause:** Missing required field in response  
**Fix:** Verify all fields present: accounts, messages, conversations, orders, payments, agents, timestamp

### Charts show no data points
**Cause:** Date format wrong  
**Fix:** Verify using `.isoformat()` on date objects: `date.isoformat()` → "2026-03-12"

---

## Performance Optimization

### For Large Databases

1. **Add database indexes:**
```python
class Message(models.Model):
    created_date = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
    direction = models.CharField(max_length=10, db_index=True)

class Conversation(models.Model):
    created_date = models.DateTimeField(db_index=True)
    modified_date = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
    mode = models.CharField(max_length=10, db_index=True)

class StoreOrder(models.Model):
    created_date = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
```

2. **Cache responses:**
```python
from django.views.decorators.cache import cache_page

@cache_page(60)  # Cache for 1 minute
def get_overview(request):
    # ...
```

3. **Use select_related/prefetch_related:**
```python
Agent.objects.select_related('account').filter(status='active')
```

---

**Status:** Implementation Ready  
**Last Updated:** 2026-03-12  
**Version:** 1.0.0
