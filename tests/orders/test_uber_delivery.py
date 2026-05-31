import pytest
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User

from apps.orders.models import StoreOrder, StoreOrderItem
from apps.stores.models import Store, Product
from apps.orders.services.uber_delivery import UberDeliveryClient


@pytest.mark.django_db
class TestUberDeliveryBugFixes(TestCase):
    """Tests for Uber Integration Bug Fixes (5 corrections)."""

    def setUp(self):
        self.client = UberDeliveryClient()
        self.owner = User.objects.create_user(
            username='owner@test.com',
            email='owner@test.com',
            password='testpass123'
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Test Store',
            slug='test-store',
            address='Rua das Flores, 123',
            city='São Paulo',
            state='SP',
            zip_code='01234-567',
        )
        self.product = Product.objects.create(
            store=self.store,
            name='Test Product',
            slug='test-product',
            price=25.00,
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            order_number='ORD001',
            status='confirmado',
            subtotal=50.00,
            total=50.00,
            customer_phone='+5511998765432',
            delivery_address={
                'street': 'Avenida Paulista',
                'number': '1000',
                'city': 'São Paulo',
                'state': 'SP',
                'zip_code': '01310-100'
            }
        )

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_bug_fix_1_oauth_scope_direct_organizations(self, mock_post):
        """
        BUG FIX #1: OAuth scope was 'eats.deliveries' (Uber Eats).
        Now corrected to 'direct.organizations' (Uber Direct DaaS).
        """
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'access_token': 'test_token',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response

        self.client._get_access_token()

        call_args = mock_post.call_args
        assert call_args[1]['data']['scope'] == 'direct.organizations'
        assert call_args[1]['data']['scope'] != 'eats.deliveries'

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_bug_fix_2_payload_nested_pickup_dropoff(self, mock_post):
        """
        BUG FIX #2: Payload was flat (pickup_address, dropoff_address as strings).
        Now uses nested objects: {pickup: {name, address, phone_number}, dropoff: {...}}
        """
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'delivery_request_id': 'req_123',
            'status': 'pending',
        }
        mock_post.return_value = mock_response

        self.client._access_token = 'fake_token'
        self.client._token_expires_at = None

        self.client.create_delivery_request(
            pickup_address='Rua das Flores, 123, São Paulo, SP, 01234-567',
            dropoff_address='Avenida Paulista, 1000, São Paulo, SP, 01310-100',
            customer_phone='+5511998765432',
            order_id='TEST-001',
            items=[{'name': 'Salada', 'quantity': 1}],
        )

        call_args = mock_post.call_args
        payload = call_args[1]['json']

        # Verify nested structure
        assert 'pickup' in payload and isinstance(payload['pickup'], dict)
        assert 'dropoff' in payload and isinstance(payload['dropoff'], dict)

        # Verify nested fields
        assert all(k in payload['pickup'] for k in ['name', 'address', 'phone_number'])
        assert all(k in payload['dropoff'] for k in ['name', 'address', 'phone_number'])

    @patch('apps.orders.tasks.UberDeliveryClient')
    def test_bug_fix_3_use_product_name_not_product_fk(self, mock_uber_client):
        """
        BUG FIX #3: Task was using item.product.name (nullable FK, could fail).
        Now uses item.product_name (denormalized field, always set).
        """
        from apps.orders.tasks import create_uber_delivery_request

        item = StoreOrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name='Test Product',
            quantity=2,
        )

        mock_client = MagicMock()
        mock_client.create_delivery_request.return_value = {
            'delivery_request_id': 'req_123',
            'status': 'pending'
        }
        mock_uber_client.return_value = mock_client

        create_uber_delivery_request(str(self.order.id), str(self.store.id))

        call_args = mock_client.create_delivery_request.call_args
        items = call_args[1]['items']

        # Verify uses product_name, not product.name
        assert items[0]['name'] == 'Test Product'

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_bug_fix_4_items_use_quantity_not_qty(self, mock_post):
        """
        BUG FIX #4: Items list used 'qty' key. Uber Direct API expects 'quantity'.
        """
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'delivery_request_id': 'req_123',
            'status': 'pending',
        }
        mock_post.return_value = mock_response

        self.client._access_token = 'fake_token'
        self.client._token_expires_at = None

        self.client.create_delivery_request(
            pickup_address='Store',
            dropoff_address='Customer',
            customer_phone='+5511999999999',
            order_id=1,
            items=[
                {'name': 'Item 1', 'quantity': 2},
                {'name': 'Item 2', 'quantity': 1},
            ]
        )

        call_args = mock_post.call_args
        payload = call_args[1]['json']

        for item in payload['items']:
            assert 'quantity' in item
            assert 'qty' not in item

    @patch('apps.orders.tasks.UberDeliveryClient')
    def test_bug_fix_5_pickup_address_complete(self, mock_uber_client):
        """
        BUG FIX #5: Pickup address only had store.address (missing city/state/zip).
        Now builds complete address: address, city, state, zip_code.
        """
        from apps.orders.tasks import create_uber_delivery_request

        item = StoreOrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name='Product',
            quantity=1,
        )

        mock_client = MagicMock()
        mock_client.create_delivery_request.return_value = {
            'delivery_request_id': 'req_123',
            'status': 'pending'
        }
        mock_uber_client.return_value = mock_client

        create_uber_delivery_request(str(self.order.id), str(self.store.id))

        call_args = mock_client.create_delivery_request.call_args
        pickup_address = call_args[1]['pickup_address']

        # Verify complete address
        assert 'Rua das Flores, 123' in pickup_address
        assert 'São Paulo' in pickup_address
        assert 'SP' in pickup_address
        assert '01234-567' in pickup_address
