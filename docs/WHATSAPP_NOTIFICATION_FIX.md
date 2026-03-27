# WhatsApp Notification Debug & Fix Report
**Date:** 2026-03-16  
**Commit:** 3ae7e3a (Enhanced logging) + 881cff2 (Initial logging)

## Problem Summary
❌ **Issue:** WhatsApp notifications not being sent to customers when order status changes  
✓ **Status Changes:** Working (database updates, timestamps, webhooks)  
✗ **Notifications:** Silent failure - no error, no success logs

## Root Cause Analysis

### Primary Cause: Incomplete Debugging Visibility
The previous implementation had **minimal logging**, making it impossible to determine where in the notification pipeline the failure occurred:
- ✂️ Early returns at validation points (no customer phone, missing template, duplicate notification)
- ✂️ Silent exception handling in try/catch blocks
- ✂️ No logging of account lookup attempts

### Secondary Causes Identified

1. **Database Migration Not Applied**
   - ❌ Migration created but not executed: `stores.0002_add_status_timestamps`
   - ✓ **Fixed:** Applied migration successfully
   - Columns added to database: `confirmed_at`, `processing_at`, `preparing_at`, `ready_at`, `out_for_delivery_at`, `picked_up_at`

2. **Missing Status Templates in Message Map**
   - ❌ Status `PROCESSING`, `PAID`, `SHIPPED`, and others had no templates
   - ✓ **Fixed:** Added complete message templates for all 11 order statuses

3. **Incomplete State Machine**
   - ❌ `pending` → `processing` transition was invalid
   - ✓ **Fixed:** Added `processing` to valid transitions in OrderService

4. **Code Module Caching in Development**
   - ⚠️ **Not Yet Fixed:** Changes to Django models require server restart in development mode
   - **Action Required:** Restart Django server or use importlib.reload()

## Solutions Implemented

### 1. Migration Applied ✓
```bash
python manage.py migrate stores 0002
# Output: Applying stores.0002_add_status_timestamps... OK
```

###  2. Enhanced Logging Added ✓
File: `server/apps/stores/models/order.py`

Added comprehensive tracing with:
- ✓ Entry point logging: `[WhatsAppNotification] START`
- ✓ Each validation point clearly logged
- ✓ Account lookup attempts with results
- ✓ Success confirmations
- ✓ Exception details with full traceback

**Example Log Output (Expected):**
```
[WhatsAppNotification] START - Order CES-160326-0001, Status: processing
[WhatsAppNotification] ✓ Message template formatted successfully
[WhatsAppNotification] ✓ Phone normalization: 5561987654321 → 5561987654321
[WhatsAppNotification] → Checking store ce-saladas for linked account...
[WhatsAppNotification] ✓ Got account from store: <account-id>
[WhatsAppNotification] → Sending message...
[WhatsAppNotification] ✓ Message sent successfully!
[WhatsAppNotification] ✓ Metadata updated and saved
```

Or if account missing (shows where it fails):
```
[WhatsAppNotification] RETURN: No WhatsApp account found (store: <id>, default: None)
```

### 3. Code Changes Summary

**File:** `server/apps/stores/models/order.py`
- **Lines 256-340:** `_trigger_status_whatsapp_notification()` method
- Enhanced with detailed logging at every decision point
- Used `getattr()` for safer attribute access
- Improved error handling with informative logs

**File:** `server/apps/stores/migrations/0002_add_status_timestamps.py`
- Creates timestamp fields for order status tracking

**File:** `server/apps/stores/services/order_service.py`
- Lines 111-120: Valid state transitions (includes `pending → processing`)


## Next Steps: To Verify the Fix Works

### Step 1: Restart Django Server
The code changes are committed but not yet loaded by the development server:
```bash
# If using: python manage.py runserver
# Kill the process (Ctrl+C) and restart
python manage.py runserver

# OR if using gunicorn/production:
docker restart pastita_web pastita_celery
```

### Step 2: Create Test Order
```bash
python manage.py shell
```

Then paste:
```python
from apps.stores.models import Store, StoreOrder
from decimal import Decimal

# Get existing store
store = Store.objects.first()  # or specify: Store.objects.get(slug='ce-saladas')

# Create test order
order = StoreOrder.objects.create(
    store=store,
    customer_name='Test Customer',
    customer_phone='5561987654321',  # Must be valid Brazilian number
    total_amount=Decimal('50.00'),
    status=StoreOrder.OrderStatus.PENDING,
)
print(f"Created order: {order.order_number}")

# Trigger notification
order.update_status(StoreOrder.OrderStatus.PROCESSING, notify=True)
print("Status updated. Check logs for [WhatsAppNotification] messages")
```

### Step 3: Check Logs
```bash
tail -f server/logs/dev.log | grep "[WhatsAppNotification]"
```

## Expected Outcomes

### ✓ Success Scenario (Messages Sending)
Logs show complete flow:
- `[WhatsAppNotification] START`
- `[WhatsAppNotification] ✓ Message template formatted`
- `[WhatsAppNotification] ✓ Phone normalization: 9999... → 5561987654321`
- `[WhatsAppNotification] ✓ Got account from store`
- `[WhatsAppNotification] ✓ Message sent successfully!`
- `[WhatsAppNotification] ✓ Metadata updated and saved`

**Result:** Customer receives WhatsApp message within 30 seconds

### ✗ Common Failure Points (Easily Diagnosed Now)

1. **No phone number:**
   ```
   [WhatsAppNotification] RETURN: No customer phone for order ORD-160326-0001
   ```
   **Fix:** Ensure `order.customer_phone` is populated

2. **No WhatsApp account:**
   ```
   [WhatsAppNotification] RETURN: No WhatsApp account found (store: <id>, default: None)
   ```
   **Fix:** Configure WhatsApp account:
   - Ensure store has linked account
   - OR configure default account in settings

3. **Account missing phone_number_id:**
   ```
   [WhatsAppNotification] RETURN: Account abc-123 missing phone_number_id
   ```
   **Fix:** Verify WhatsApp account setup with Meta API

4. **Invalid phone after normalization:**
   ```
   [WhatsAppNotification] RETURN: Invalid phone number 123
   ```
   **Fix:** Use valid international format (starts with country code)

## Configuration Verification Checklist

- [ ] **Migration Applied:** `python manage.py migrate stores 0002`
- [ ] **Server Restarted:** Django server or Docker containers
- [ ] **WhatsApp Account Configured:** `WhatsAppAccount` model has valid data
- [ ] **Phone Format Valid:** Customer phone in international format
- [ ] **Logs Being Generated:** New `[WhatsAppNotification]` messages visible

## Files Modified (Git Commits)

1. **881cff2** - "Improvement: Add detailed logging to WhatsApp notification method"
   - Initial comprehensive logging setup
   
2. **3ae7e3a** - "Improvement: Enhance WhatsApp notification logging with better visibility"
   - Visual logging enhancements (✓, ✗, →)
   - Better debugging context
   - Safer attribute access

## Testing Tools Created

Created helper scripts in `server/` directory:
- `test_with_existing_store.py` - Test with actual store
- `check_whatsapp_accounts.py` - Verify account configuration
- `create_test_order.py` - Create orders for testing

Run with:
```bash
python manage.py shell < test_with_existing_store.py
```

## Support & Troubleshooting

If notifications still not sending after restart:

1. **Check logs first:** Look for `[WhatsAppNotification]` messages
2. **Run test:** `python manage.py shell < check_whatsapp_accounts.py`
3. **Check account:** Ensure `WhatsAppAccount.objects.all().first().phone_number_id` is not None
4. **Verify phone:** Test number must be in international format

---
**Status:** ✓ Ready For Testing  
**Priority:** HIGH - Customer notifications critical for order management  
**Next Review:** After server restart and test execution
