#!/usr/bin/env python
"""Test script to verify WhatsApp notification flow."""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(__file__))

django.setup()

from apps.stores.models import StoreOrder
from django.utils import timezone
import json

# Attempt to find a recent order and test notification
try:
    # Get the most recent order
    order = StoreOrder.objects.order_by('-created_at').first()
    
    if not order:
        print("No orders found in the database.")
        sys.exit(0)
    
    print(f"\n{'='*60}")
    print(f"Testing WhatsApp notification for Order: {order.order_number}")
    print(f"{'='*60}")
    print(f"Order ID: {order.id}")
    print(f"Current Status: {order.status}")
    print(f"Customer Name: {order.customer_name}")
    print(f"Customer Phone: {order.customer_phone}")
    print(f"Store: {order.store}")
    print(f"Metadata (notification flags): {json.dumps({k: v for k, v in order.metadata.items() if 'notification' in k}, indent=2)}")
    
    # Test with status change
    if order.status != StoreOrder.OrderStatus.CONFIRMED:
        print(f"\nChanging status from {order.status} to CONFIRMED...")
        order.update_status(StoreOrder.OrderStatus.CONFIRMED, notify=True)
        print(f"Status changed successfully!")
        print(f"Updated metadata: {json.dumps({k: v for k, v in order.metadata.items() if 'notification' in k}, indent=2)}")
    else:
        # Try processing
        print(f"\nChanging status from {order.status} to PROCESSING...")
        order.update_status(StoreOrder.OrderStatus.PROCESSING, notify=True)
        print(f"Status changed successfully!")
        print(f"Updated metadata: {json.dumps({k: v for k, v in order.metadata.items() if 'notification' in k}, indent=2)}")
    
    print(f"\n{'='*60}")
    print("Test completed! Check the logs for [WhatsAppNotification] messages.")
    print(f"{'='*60}\n")

except Exception as e:
    print(f"Error during test: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
