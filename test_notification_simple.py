from apps.stores.models import Store, StoreOrder, StoreProduct, StoreOrderItem
from decimal import Decimal

print("\n" + "=" * 70)
print("CREATING TEST ORDER AND TESTING WHATSAPP NOTIFICATIONS")
print("=" * 70 + "\n")

# Get or create a test store
store, _ = Store.objects.get_or_create(
    slug='test-store',
    defaults={
        'name': 'Test Store for WhatsApp Notifications',
        'city': 'Test City',
        'state': 'Test State',
        'country': 'Test Country'
    }
)
print(f"✓ Using store: {store.name}")

# Get or create a test product
product, _ = StoreProduct.objects.get_or_create(
    store=store,
    name='Test Product',
    defaults={
        'price': Decimal('10.00'),
        'sku': 'TEST-SKU-001'
    }
)
print(f"✓ Using product: {product.name}")

# Create a test order
order = StoreOrder.objects.create(
    store=store,
    customer_name='Test Customer',
    customer_phone='5561987654321',
    customer_email='test@example.com',
    status=StoreOrder.OrderStatus.PENDING,
    total_amount=Decimal('10.00'),
)
print(f"✓ Created order: {order.order_number} (ID: {order.id})")
print(f"  Phone: {order.customer_phone}")

# Add an item to the order
StoreOrderItem.objects.create(
    order=order,
    product=product,
    quantity=1,
    unit_price=Decimal('10.00'),
)
print(f"✓ Added product to order")

# Test status change to PROCESSING first
print(f"\n{'─' * 70}")
print("TEST 1: Changing status from PENDING → PROCESSING")
print(f"{'─' * 70}")
order.update_status(StoreOrder.OrderStatus.PROCESSING, notify=True)
print(f"✓ Status updated successfully")
notification_flag = order.metadata.get('whatsapp_notification_processing', 'NOT SET')
print(f"  Notification flag: {notification_flag}")

# Test status change to CONFIRMED
print(f"\n{'─' * 70}")
print("TEST 2: Changing status from PROCESSING → CONFIRMED")
print(f"{'─' * 70}")
order.update_status(StoreOrder.OrderStatus.CONFIRMED, notify=True)
print(f"✓ Status updated successfully")
notification_flag = order.metadata.get('whatsapp_notification_confirmed', 'NOT SET')
print(f"  Notification flag: {notification_flag}")

print(f"\n{'=' * 70}")
print("COMPLETED! Check the log file for [WhatsAppNotification] messages.")
print(f"Log file location: server/logs/dev.log")
print(f"{'=' * 70}\n")
