# Uber Delivery Dispatch Modal — Design Spec
**Date:** 2026-05-29  
**Project:** Ce Saladas (cardapidex)  
**Status:** Design Phase  

---

## Overview

Ce Saladas needs to dispatch Uber drivers for deliveries during the transition period before their own Toca Delivery service is fully operational. This spec adds a manual dispatch button to the order management dashboard (`/stores/{slug}/orders`) that lets store managers request an Uber driver via modal UI with real-time polling for driver assignment.

**Goal:** When a store manager clicks a "request delivery" button on an order, they should see driver details and have the option to accept or reject and retry.

---

## Requirements

### Functional
1. **Manual dispatch trigger** — SVG moto icon button on each order row in `/stores/{slug}/orders`
2. **Modal interaction** — Opens modal on button click
3. **Driver search** — Backend creates Uber delivery request; modal polls for driver assignment
4. **Driver details display** — Name, phone, vehicle, ETA, pickup instructions
5. **Rejection flow** — User can reject driver and retry search (same order)
6. **Cancellation** — Reject button cancels Uber delivery request server-side

### Non-Functional
- Polling interval: 3 seconds (until driver found or timeout)
- Timeout: 60 seconds (then show "no drivers available")
- Only one active delivery request per order
- Works for Ce Saladas store only (multi-tenant aware via `{slug}`)

---

## Architecture

### Data Model Changes

**StoreOrder model additions:**
```python
class StoreOrder(models.Model):
    # ... existing fields ...
    
    # Delivery provider tracking
    DELIVERY_PROVIDER_CHOICES = [
        ('none', 'None'),
        ('toca', 'Toca Delivery'),
        ('uber', 'Uber Eats'),
    ]
    delivery_provider = models.CharField(
        max_length=10, 
        choices=DELIVERY_PROVIDER_CHOICES, 
        default='none'
    )
    
    # Uber fields
    uber_delivery_request_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Uber's delivery request ID"
    )
    uber_driver_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True
    )
    uber_driver_name = models.CharField(max_length=255, blank=True)
    uber_driver_phone = models.CharField(max_length=20, blank=True)
    uber_vehicle_info = models.CharField(max_length=255, blank=True)
    uber_eta_minutes = models.IntegerField(blank=True, null=True)
    uber_pickup_instructions = models.TextField(blank=True)
    uber_created_at = models.DateTimeField(blank=True, null=True)
```

### API Endpoints

#### 1. Create Delivery Request
**POST** `/api/v1/stores/{slug}/orders/{order_id}/create-delivery-request`

**Request:**
```json
{}
```

**Response (202 Accepted):**
```json
{
  "delivery_request_id": "uber_req_12345",
  "status": "searching",
  "message": "Driver search started. Check status endpoint."
}
```

**Logic:**
- Validate order exists and belongs to store
- Check order state (should be confirmed/preparando, not cancelled)
- Call Uber API to create delivery request with order details (pickup address, dropoff, items)
- Store `uber_delivery_request_id` in StoreOrder
- Return immediately (don't wait for driver)

#### 2. Poll Driver Status
**GET** `/api/v1/stores/{slug}/orders/{order_id}/delivery-request-status`

**Response (200 OK — driver found):**
```json
{
  "status": "driver_found",
  "driver": {
    "id": "driver_123",
    "name": "João Silva",
    "phone": "+55 11 99999-9999",
    "vehicle": "Honda Civic Branco - ABC 1234",
    "rating": 4.8,
    "eta_minutes": 12,
    "pickup_instructions": "Ring doorbell twice"
  }
}
```

**Response (200 OK — still searching):**
```json
{
  "status": "searching",
  "message": "No drivers available yet. Retrying..."
}
```

**Response (408 Timeout):**
```json
{
  "status": "no_drivers",
  "message": "No drivers found in 60 seconds. Try again later."
}
```

**Logic:**
- Query Uber API using stored `uber_delivery_request_id`
- If driver assigned: store driver fields, return driver details
- If still searching: return "searching"
- If timeout (60s): return "no_drivers"

#### 3. Cancel Delivery Request
**DELETE** `/api/v1/stores/{slug}/orders/{order_id}/delivery-request`

**Response (200 OK):**
```json
{
  "status": "cancelled",
  "message": "Delivery request cancelled. You can retry."
}
```

**Logic:**
- Cancel on Uber side using `uber_delivery_request_id`
- Clear Uber fields from StoreOrder (except provider="uber" for audit)
- Allow user to call create-delivery-request again

---

## Frontend: Modal UI

### Button Trigger
- **Location:** Order row in `/stores/{slug}/orders` table
- **Icon:** SVG moto/scooter icon (or motorcycle)
- **Label:** "Request Delivery" (on hover) or icon-only
- **Disabled state:** If order not in confirmado/preparando or already has active delivery_provider
- **Show only for Ce Saladas:** Store slug check

### Modal States

**State 1: Searching**
```
┌─────────────────────────────────┐
│ Requesting Uber Driver          │
├─────────────────────────────────┤
│                                 │
│ 🔄 Searching for available      │
│    drivers...                   │
│                                 │
│ [Cancel]                        │
└─────────────────────────────────┘
```

**State 2: Driver Found**
```
┌─────────────────────────────────┐
│ Driver Assigned ✓               │
├─────────────────────────────────┤
│ João Silva                      │
│ ⭐ 4.8 (2,341 trips)            │
│                                 │
│ 📱 +55 11 99999-9999            │
│ 🚗 Honda Civic Branco - ABC 1234│
│                                 │
│ ⏱️ ETA: 12 minutes              │
│ 📍 Pickup: Ring doorbell twice  │
│                                 │
│ [Reject & Try Again]  [Accept]  │
└─────────────────────────────────┘
```

**State 3: No Drivers**
```
┌─────────────────────────────────┐
│ No Drivers Available            │
├─────────────────────────────────┤
│ ❌ Couldn't find drivers in the │
│    area. Try again later.       │
│                                 │
│ [Close]                         │
└─────────────────────────────────┘
```

### User Actions

| Action | Trigger | Behavior |
|--------|---------|----------|
| **Reject & Try Again** | Button during "Driver Found" | DELETE endpoint → clear fields → reset modal to "Searching" → user can retry create-delivery-request |
| **Accept** | Button during "Driver Found" | Close modal → update order view to show delivery provider = "uber" + driver name |
| **Cancel** (searching) | Button during "Searching" | DELETE endpoint → close modal |

---

## Implementation: Backend Flow

### Celery Task (Optional Async)
```python
@shared_task
def create_uber_delivery_request(order_id: int, store_id: int):
    """
    Create delivery request on Uber side.
    Called from view after validation.
    """
    order = StoreOrder.objects.get(id=order_id, store_id=store_id)
    
    # Call Uber API (stub here)
    uber_response = uber_api.create_delivery_request({
        'pickup_address': order.store.address,
        'dropoff_address': order.delivery_address,
        'items': [{'name': item.name, 'qty': item.qty} for item in order.items.all()],
        'customer_phone': order.customer_phone,
    })
    
    order.uber_delivery_request_id = uber_response['delivery_request_id']
    order.delivery_provider = 'uber'
    order.save()
    
    return uber_response['delivery_request_id']
```

### Error Handling
- **Invalid order state:** 400 Bad Request ("Order must be confirmed before requesting delivery")
- **Duplicate request:** 409 Conflict ("Delivery already requested for this order")
- **Uber API failure:** 502 Bad Gateway ("Failed to reach Uber. Try again.")
- **Network timeout (polling):** Auto-retry 3 times before showing "no drivers"

---

## Testing Strategy

### Unit Tests
- `test_create_delivery_request_valid_order` — Happy path
- `test_create_delivery_request_invalid_state` — Order not confirmed
- `test_cancel_delivery_request` — Cancellation clears fields
- `test_poll_driver_timeout` — 60s timeout behavior

### Integration Tests
- `test_modal_flow_end_to_end` — Create → Poll → Accept
- `test_modal_reject_and_retry` — Create → Poll → Reject → Create again

### Manual Testing (Dashboard)
- Button disabled for non-Ce-Saladas stores
- Button disabled if order cancelled
- Modal polling updates driver name/ETA correctly
- Reject button works and resets modal
- Accept button closes modal and updates order view

---

## Deployment Checklist

- [ ] Add StoreOrder fields (migration)
- [ ] Create API endpoints with auth
- [ ] Create Celery task (if async)
- [ ] Add Uber API client wrapper
- [ ] Frontend: Button component + Modal component
- [ ] Frontend: Polling logic (3s interval, 60s timeout)
- [ ] Tests pass (unit + integration)
- [ ] Manual QA on staging
- [ ] Uber sandbox credentials configured
- [ ] Error messages localized (PT-BR)

---

## Rollback Plan

If Uber integration fails post-deploy:
1. Disable button via feature flag (store `delivery_enabled=False`)
2. Clear active delivery requests (management command)
3. Revert to manual delivery assignment

---

## Future: Toca Delivery Transition

Once Toca is operational:
1. Change `delivery_provider` from "uber" to "toca" in environment
2. Modal calls Toca API instead (same modal UI, different backend)
3. Keep historical Uber records for audit
4. Eventually archive Uber fields

---

## References

- Uber API docs: https://github.com/199-mcp/mcp-uber (user reference)
- Toca Delivery integration: `docs/TOCA_DELIVERY_INTEGRATION.md`
- Existing delivery zones: `apps/stores/models.py` → `StoreDeliveryZone`
