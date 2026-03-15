# Frontend Integration Requirements

## Overview
This document outlines the specific requirements for the pastita-dash frontend to correctly receive and display dashboard data from the Django backend API.

## API Endpoints

### 1. `/api/core/dashboard/overview/` - GET

**Response Structure (DashboardOverview):**
```json
{
  "accounts": {
    "total": 42
  },
  "messages": {
    "today": 156,
    "by_direction": {
      "inbound": 78,
      "outbound": 78
    },
    "by_status": {
      "sent": 10,
      "delivered": 50,
      "read": 15,
      "failed": 2,
      "pending": 1
    }
  },
  "conversations": {
    "active": 12,
    "by_mode": {
      "auto": 7,
      "human": 3,
      "hybrid": 2
    },
    "by_status": {
      "open": 8,
      "closed": 2,
      "pending": 1,
      "resolved": 1
    }
  },
  "orders": {
    "today": 5,
    "by_status": {
      "pending": 1,
      "confirmed": 1,
      "processing": 1,
      "paid": 1,
      "preparing": 0,
      "ready": 0,
      "shipped": 0,
      "out_for_delivery": 0,
      "delivered": 1,
      "completed": 0,
      "cancelled": 0,
      "refunded": 0,
      "failed": 0
    }
  },
  "payments": {
    "pending": 2,
    "confirmed": 3,
    "amount_today": 450.00
  },
  "agents": {
    "active": 3,
    "interactions_today": 145,
    "avg_duration_ms": 1250,
    "resolved_today": 21
  },
  "timestamp": "2026-03-12T10:30:45Z"
}
```

**Required Fields (CRITICAL):**
- ✅ `accounts.total` - Total account count (integer)
- ✅ `messages.today` - Messages sent/received today (integer)
- ✅ `messages.by_direction` - Breakdown: `{inbound, outbound}` (integers)
- ✅ `messages.by_status` - Breakdown: `{sent, delivered, read, failed, pending}` (integers)
- ✅ `conversations.active` - Active conversations count (integer)
- ✅ `conversations.by_mode` - Breakdown: `{auto, human, hybrid}` (integers)
- ✅ `conversations.by_status` - Breakdown: `{open, closed, pending, resolved}` (integers)
- ✅ `orders.today` - Orders created today (integer)
- ✅ `orders.by_status` - All 13 status values expected (integers, min 0)
- ✅ `payments.pending` - Pending payments count (integer)
- ✅ `payments.confirmed` - Confirmed payments count (integer)
- ✅ `payments.amount_today` - Today's revenue (float/decimal)
- ✅ `agents.active` - Active AI agents count (integer)
- ✅ `agents.interactions_today` - AI interactions count (integer) **[PREVIOUSLY MISSING - NOW CRITICAL]**
- ✅ `agents.avg_duration_ms` - Average interaction duration in milliseconds (integer) **[PREVIOUSLY MISSING - NOW CRITICAL]**
- ✅ `agents.resolved_today` - Conversations resolved by AI today (integer)
- ✅ `timestamp` - ISO 8601 timestamp (string)

**Field NOT Expected (Frontend Removed):**
- ❌ `orders.total_value` - Not used, `payments.amount_today` preferred
- ❌ Direct delivery rate - Frontend calculates: `(delivered + read) / outbound * 100`

---

### 2. `/api/core/dashboard/charts/` - GET

**Query Parameters:**
- `days` (integer, 1-90, default: 30) - Number of days for historical data

**Response Structure (DashboardCharts):**
```json
{
  "messages_per_day": [
    {"date": "2026-03-12", "count": 42},
    {"date": "2026-03-11", "count": 38},
    {"date": "2026-03-10", "count": 45}
  ],
  "orders_per_day": [
    {"date": "2026-03-12", "count": 5},
    {"date": "2026-03-11", "count": 3},
    {"date": "2026-03-10", "count": 7}
  ],
  "conversations_per_day": [
    {
      "date": "2026-03-12",
      "new": 3,
      "resolved": 2
    },
    {
      "date": "2026-03-11",
      "new": 2,
      "resolved": 1
    },
    {
      "date": "2026-03-10",
      "new": 5,
      "resolved": 4
    }
  ],
  "message_types": {
    "text": 850,
    "image": 120,
    "audio": 45,
    "video": 15,
    "document": 8
  },
  "order_statuses": {
    "pending": 2,
    "confirmed": 1,
    "processing": 3,
    "paid": 5,
    "preparing": 2,
    "ready": 1,
    "shipped": 8,
    "out_for_delivery": 4,
    "delivered": 25,
    "completed": 18,
    "cancelled": 3,
    "refunded": 1,
    "failed": 2
  }
}
```

**Required Fields (CRITICAL):**
- ✅ `messages_per_day[]` - Array of `{date: YYYY-MM-DD, count: integer}`
- ✅ `orders_per_day[]` - Array of `{date: YYYY-MM-DD, count: integer}`
- ✅ `conversations_per_day[]` - Array of `{date: YYYY-MM-DD, new: integer, resolved: integer}` **[EXPANDED - NOW SHOWS NEW vs RESOLVED]**
- ✅ `message_types` - Distribution object (optional fields okay, must be integers)
- ✅ `order_statuses` - All 13 status types (integers, min 0)

**Date Format:** ISO 8601 (YYYY-MM-DD) - **MUST** be sorted ascending (oldest first)

---

## Type Definitions

The frontend has comprehensive TypeScript types in `pastita-dash/src/types/dashboard.ts`:

```typescript
// Message enums
type MessageDirection = 'inbound' | 'outbound';
type MessageStatus = 'sent' | 'delivered' | 'read' | 'failed' | 'pending';

// Conversation enums
type ConversationMode = 'auto' | 'human' | 'hybrid';
type ConversationStatus = 'open' | 'closed' | 'pending' | 'resolved';

// Order enums
type OrderStatus =
  | 'pending'
  | 'confirmed'
  | 'processing'
  | 'paid'
  | 'preparing'
  | 'ready'
  | 'shipped'
  | 'out_for_delivery'
  | 'delivered'
  | 'completed'
  | 'cancelled'
  | 'refunded'
  | 'failed';

// Payment enums
type PaymentStatus = 'pending' | 'confirmed' | 'failed' | 'cancelled' | 'refunded' | 'processing';
```

---

## Backend Validation Checklist

### DashboardOverviewView (`apps/core/dashboard_views.py`)

✅ **Required Implementation:**
1. Query `Agent.objects.filter(status='active').count()` → `agents.active`
2. Query `Agent.objects.aggregate(Sum('interactions_today'))` → `agents.interactions_today`
3. Query `Agent.objects.aggregate(Avg('avg_duration_ms'))` → `agents.avg_duration_ms` (or calculate from interactions)
4. Query `Conversation.objects.filter(status='resolved', created_date__date=today).count()` → `agents.resolved_today`
5. Annotate all `by_*` dictionaries with exact keys shown above
6. Ensure `conversations_per_day` shows true breakdown (not just aggregates)
7. Return ISO 8601 timestamps (use Django's `timezone.now().isoformat()`)

### DashboardChartsView (`apps/core/dashboard_views.py`)

✅ **Required Implementation:**
1. Parse `days` parameter: `max(1, min(int(request.GET.get('days', 30)), 90))`
2. Calculate date range from `today - days` to `today`
3. Return `conversations_per_day` with **two separate counts**: `new` and `resolved`
   - `new`: Conversations created on that date
   - `resolved`: Conversations marked resolved on that date (NOT created)
4. Ensure arrays are sorted ascending by date
5. Validate all numeric values are non-negative
6. All counts cast to integers (no floats in counts)

---

## Frontend Validation

The frontend (`pastita-dash/src/utils/dashboardValidators.ts`) implements:

1. **Structure Validation** - Ensures all required fields exist
2. **Type Validation** - Confirms fields are correct type (number, string, array, object)
3. **Enum Validation** - Validates that status/mode/direction values are valid
4. **Safe Defaults** - Falls back to 0 for numbers, empty objects for distributions
5. **Error Logging** - Logs `[Dashboard]` prefixed warnings to browser console

---

## Common Issues & Fixes

### Issue: Frontend shows "0" for all metrics
- **Cause:** Backend returns `null` or fields missing
- **Fix:** Ensure all `by_*` dictionaries returned (even if empty `{}`)
- **Fallback:** Frontend assumes 0 if field missing

### Issue: Conversation modes not displayed
- **Cause:** `conversations.by_mode` missing from response
- **Fix:** Add `ConversationMode` annotation to query
- **Frontend:** Shows "Sem conversas" if no modes found

### Issue: Agent metrics empty
- **Cause:** `agents` object missing or incomplete
- **Fix:** Query `Agent` model for interactions and duration
- **Frontend:** Shows 0 interactions and "0ms med." if missing

### Issue: Charts not showing data points
- **Cause:** Date format wrong (not YYYY-MM-DD) or arrays not sorted
- **Fix:** Use `date.isoformat()` and `order_by('date')`
- **Frontend:** Shows "Carregando..." if dates can't be parsed

### Issue: Delivery rate calculation wrong
- **Cause:** Missing `by_status` breakdown
- **Fix:** Aggregate by `message_status` enum values
- **Frontend:** Calculates `(delivered + read) / outbound * 100`, ensure outbound field exists

---

## Testing Checklist

✅ **Manual Testing:**
1. Call `/api/core/dashboard/overview/` → Verify JSON structure matches above
2. Call `/api/core/dashboard/charts/?days=7` → Verify arrays sorted by date
3. Check browser console → Should NOT see `[Dashboard]` warnings
4. Check stat cards render → Should show real numbers (not 0)
5. Check Health card → Should show conversation mode breakdown
6. Check Charts → Should show 3 charts with real data

✅ **Automated Testing:**
```bash
# In pastita-dash/
npm test -- DashboardPage.test.tsx
npm test -- dashboardService.test.tsx
npm test -- dashboardValidators.test.ts
```

✅ **Integration Testing:**
```bash
# Start backend
python manage.py runserver

# In pastita-dash/
npm start

# Open http://localhost:3000/dashboard
# Check Network tab for API responses
# Verify all data matches backend
```

---

## Serializer Template

If not already present, add to `apps/core/serializers.py`:

```python
from rest_framework import serializers
from apps.agents.models import Agent
from apps.conversations.models import Conversation
from apps.stores.models import StoreOrder, StorePaymentGateway

class DashboardOverviewSerializer(serializers.Serializer):
    """Serializes dashboard overview metrics"""
    accounts = serializers.DictField(child=serializers.IntegerField())
    messages = serializers.DictField()
    conversations = serializers.DictField()
    orders = serializers.DictField()
    payments = serializers.DictField()
    agents = serializers.DictField()
    timestamp = serializers.DateTimeField()

class DashboardChartsSerializer(serializers.Serializer):
    """Serializes dashboard chart data"""
    messages_per_day = serializers.ListField(child=serializers.DictField())
    orders_per_day = serializers.ListField(child=serializers.DictField())
    conversations_per_day = serializers.ListField(child=serializers.DictField())
    message_types = serializers.DictField(required=False)
    order_statuses = serializers.DictField(required=False)
```

---

## Updated Dashboard Endpoints

### Endpoint: `/api/core/dashboard/overview/`
- ✅ Returns all required metrics
- ✅ No hallucinations (all data from database)
- ✅ Handles timezone correctly (uses Django's `timezone.now()`)
- ✅ Returns at minimum the structure shown above

### Endpoint: `/api/core/dashboard/charts/`
- ✅ Accepts `days` parameter (1-90)
- ✅ Returns sorted date ranges
- ✅ Shows new vs resolved conversations separately
- ✅ All counts are non-negative integers

---

## Summary of Changes from Original

| Item | Original | Updated | Impact |
|------|----------|---------|--------|
| Agent metrics | Absent/Hardcoded | Real from Agent model | Accurate interactions count |
| Conversation modes | Shown in data but hidden in UI | Shown in Health card | Better conversation visibility |
| Conversations chart | Single aggregation | Split to new/resolved | Better trend analysis |
| Stat cards | 4 cards | 5 cards (added Agent IA) | More complete overview |
| Type safety | generic Record<string,number> | Specific types + validators | Fewer runtime errors |
| Chart columns | 2 columns | 3 columns | Better responsive layout |

---

**Last Updated:** 2026-03-12
**Frontend Version:** pastita-dash refactor complete
**Backend Version:** Requires FRONTEND_INTEGRATION_REQUIREMENTS compliance
