from apps.stores.models import Store, StoreOrder
from decimal import Decimal

# Get an existing store or create a simple test
stores = Store.objects.all()[:1]
if not stores:
    print("No stores found! Creating a test would need valid owner data.")
else:
    store = stores[0]
    print(f"\n✓ Found store: {store.name} (ID: {store.id})")
    
    # Create a test order with MINIMAL data
    order = StoreOrder.objects.create(
        store=store,
        customer_name='Test Customer',
        customer_phone='5561987654321',
        total_amount=Decimal('10.00'),
        status=StoreOrder.OrderStatus.PENDING,
    )
    print(f"✓ Created order: {order.order_number}")
    print(f"  Current status: {order.status}")
    print(f"  Customer phone: {order.customer_phone}")
    
    # Change status to trigger notification
    print(f"\n➤ Changing status to PROCESSING...")
    order.update_status(StoreOrder.OrderStatus.PROCESSING, notify=True)
    print(f"✓ Status updated!")
    
    # Check if notification was recorded
    notify_key = 'whatsapp_notification_processing'
    if order.metadata.get(notify_key):
        print(f"✓ Notification recorded: {order.metadata.get(notify_key)}")
    else:
        print(f"⚠ Notification NOT recorded (check logs)")
    
    print(f"\n✅ Test complete! Check logs/dev.log for [WhatsAppNotification] messages")
