#!/usr/bin/env python
"""Create a test order and trigger WhatsApp notification."""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(__file__))

django.setup()

from apps.stores.models import Store, StoreOrder, StoreProduct, StoreOrderItem
from decimal import Decimal
from django.utils import timezone

print("\n" + "=" * 70)
print("CREATING TEST ORDER AND TESTING WHATSAPP NOTIFICATIONS")
print("=" * 70 + "\n")

try:
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
        customer_phone='5561987654321',  # Test phone number (Brazilian format)
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
    print(f"  Current metadata: {order.metadata.get('whatsapp_notification_processing', 'NOT SET')}")

    # Test status change to CONFIRMED
    print(f"\n{'─' * 70}")
    print("TEST 2: Changing status from PROCESSING → CONFIRMED")
    print(f"{'─' * 70}")
    order.update_status(StoreOrder.OrderStatus.CONFIRMED, notify=True)
    print(f"✓ Status updated successfully")
    print(f"  Current metadata: {order.metadata.get('whatsapp_notification_confirmed', 'NOT SET')}")

    print(f"\n{'=' * 70}")
    print("COMPLETED! Check the log file for [WhatsAppNotification] messages.")
    print(f"{'=' * 70}\n")

except Exception as e:
    print(f"✗ Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
