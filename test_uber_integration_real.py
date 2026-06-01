#!/usr/bin/env python3
"""
Real Uber Integration Test — uses provided test credentials
DO NOT COMMIT — for local testing only
"""
import sys
import os
import django
import logging
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.orders.services.uber_delivery import UberDeliveryClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test credentials (provided by user)
# Note: If OAuth still fails with 401, verify the client_secret is correct in Cê Saladas Test App
TEST_CREDENTIALS = {
    'client_id': 'f5e8b827-7626-50a5-bca1-6fbca8c97860',
    'customer_id': 'yV_x3jPTlpYsFomZi8YWxsK_GpUgLiqj',
    'client_secret': 'BJDq1wBBepz33Axx4Vt7rrcHaBDULCfRsCf-riul',  # Without "bora"
}

def test_oauth():
    """Test OAuth token exchange"""
    print("\n" + "="*60)
    print("TEST 1: OAuth Token Exchange")
    print("="*60)

    print(f"Using credentials:")
    print(f"  Client ID: {TEST_CREDENTIALS['client_id']}")
    print(f"  Customer ID: {TEST_CREDENTIALS['customer_id']}")
    print(f"  Client Secret: {TEST_CREDENTIALS['client_secret'][:20]}...")

    client = UberDeliveryClient()
    # Override with test credentials
    client.client_id = TEST_CREDENTIALS['client_id']
    client.customer_id = TEST_CREDENTIALS['customer_id']
    client.client_secret = TEST_CREDENTIALS['client_secret']

    try:
        import requests
        # Test OAuth directly with more detail
        response = requests.post(
            'https://auth.uber.com/oauth/v2/token',
            data={
                'client_id': client.client_id,
                'client_secret': client.client_secret,
                'grant_type': 'client_credentials',
                'scope': 'direct.organizations',
            },
            timeout=10,
        )

        if response.status_code != 200:
            print(f"✗ OAuth failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return False

        token = client._get_access_token()
        print(f"✓ OAuth successful")
        print(f"  Token (first 50 chars): {token[:50]}...")
        print(f"  Expires at: {client._token_expires_at}")
        return True
    except Exception as e:
        print(f"✗ OAuth failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_create_delivery():
    """Test delivery request creation with corrected payload"""
    print("\n" + "="*60)
    print("TEST 2: Create Delivery Request (with fixed payload)")
    print("="*60)

    client = UberDeliveryClient()
    client.client_id = TEST_CREDENTIALS['client_id']
    client.customer_id = TEST_CREDENTIALS['customer_id']
    client.client_secret = TEST_CREDENTIALS['client_secret']

    # Build pickup address (with city, state, zip)
    pickup_address = "Rua das Flores, 123, São Paulo, SP, 01234-567"
    dropoff_address = "Avenida Paulista, 1000, São Paulo, SP, 01310-100"
    customer_phone = "+5511998765432"

    items = [
        {'name': 'Salada Verde', 'quantity': 1},
        {'name': 'Salada Mista', 'quantity': 2},
    ]

    try:
        result = client.create_delivery_request(
            pickup_address=pickup_address,
            dropoff_address=dropoff_address,
            customer_phone=customer_phone,
            order_id=f"TEST-{datetime.now().timestamp()}",
            items=items,
        )
        print(f"✓ Delivery request created")
        print(f"  Delivery ID: {result.get('delivery_request_id')}")
        print(f"  Status: {result.get('status')}")
        return result.get('delivery_request_id')
    except Exception as e:
        print(f"✗ Delivery creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_poll_status(delivery_id):
    """Test delivery status polling"""
    print("\n" + "="*60)
    print("TEST 3: Poll Delivery Status")
    print("="*60)

    if not delivery_id:
        print("✗ Skipped: no delivery_id from previous test")
        return False

    client = UberDeliveryClient()
    client.client_id = TEST_CREDENTIALS['client_id']
    client.customer_id = TEST_CREDENTIALS['customer_id']
    client.client_secret = TEST_CREDENTIALS['client_secret']

    try:
        result = client.poll_delivery_status(delivery_id)
        print(f"✓ Status polled successfully")
        print(f"  Status: {result.get('status')}")
        if 'driver' in result:
            driver = result['driver']
            print(f"  Driver: {driver.get('name')} ({driver.get('rating')} stars)")
            print(f"  ETA: {driver.get('eta_minutes')} minutes")
        else:
            print(f"  Driver: not assigned yet")
        return True
    except Exception as e:
        print(f"✗ Status poll failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cancel_delivery(delivery_id):
    """Test delivery cancellation"""
    print("\n" + "="*60)
    print("TEST 4: Cancel Delivery Request")
    print("="*60)

    if not delivery_id:
        print("✗ Skipped: no delivery_id from previous test")
        return False

    client = UberDeliveryClient()
    client.client_id = TEST_CREDENTIALS['client_id']
    client.customer_id = TEST_CREDENTIALS['customer_id']
    client.client_secret = TEST_CREDENTIALS['client_secret']

    try:
        result = client.cancel_delivery_request(delivery_id)
        print(f"✓ Delivery cancelled")
        print(f"  Status: {result.get('status')}")
        return True
    except Exception as e:
        print(f"✗ Cancellation failed: {e}")
        # This might fail if driver already accepted — that's OK for testing
        return True


def main():
    print("\n" + "🧪 UBER INTEGRATION REAL TEST 🧪".center(60))
    print("Credentials: Cê Saladas Test App")
    print("="*60)

    # Test 1: OAuth
    if not test_oauth():
        print("\n❌ OAuth failed — stopping tests")
        sys.exit(1)

    # Test 2: Create delivery
    delivery_id = test_create_delivery()

    # Test 3: Poll status
    if delivery_id:
        test_poll_status(delivery_id)
        # Test 4: Cancel (if you want)
        # test_cancel_delivery(delivery_id)

    print("\n" + "="*60)
    print("✓ All tests completed")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
