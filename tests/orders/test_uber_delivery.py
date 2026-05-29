import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone

from orders.models import Store, StoreOrder, OrderStatus
from orders.services.uber_delivery import UberDeliveryClient


@pytest.mark.django_db
class TestUberDeliveryClient:
    """Tests for UberDeliveryClient service layer."""

    def setup_method(self):
        """Setup test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            owner=self.user,
            whatsapp='+5511999999999',
            uber_client_id='test_client_id',
            uber_client_secret='test_client_secret',
            uber_restaurant_id='test_restaurant_id'
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_phone='+5511988888888',
            customer_name='Test Customer',
            status=OrderStatus.CONFIRMED,
            total_price=50.00,
            delivery_address='Rua Test, 123, São Paulo, SP'
        )

    @patch('orders.services.uber_delivery.requests.post')
    def test_create_delivery_request_success(self, mock_post):
        """Test successful Uber delivery request creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'delivery_id': 'uber_delivery_123',
            'status': 'scheduled',
            'pickup': {
                'location': {
                    'address': 'Store Address'
                }
            },
            'dropoff': {
                'location': {
                    'address': 'Customer Address'
                }
            }
        }
        mock_post.return_value = mock_response

        client = UberDeliveryClient(self.store)
        result = client.create_delivery_request(
            order=self.order,
            pickup_address='Rua Store, 100, São Paulo, SP',
            dropoff_address='Rua Test, 123, São Paulo, SP',
            dropoff_name='Test Customer',
            dropoff_phone='+5511988888888'
        )

        assert result is not None
        assert result['delivery_id'] == 'uber_delivery_123'
        assert result['status'] == 'scheduled'
        mock_post.assert_called_once()

    @patch('orders.services.uber_delivery.requests.post')
    def test_create_delivery_request_failure(self, mock_post):
        """Test Uber delivery request creation failure."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'error': 'invalid_request',
            'message': 'Delivery address is not deliverable'
        }
        mock_post.return_value = mock_response

        client = UberDeliveryClient(self.store)

        with pytest.raises(Exception):
            client.create_delivery_request(
                order=self.order,
                pickup_address='Rua Store, 100, São Paulo, SP',
                dropoff_address='Invalid Address',
                dropoff_name='Test Customer',
                dropoff_phone='+5511988888888'
            )

    @patch('orders.services.uber_delivery.requests.get')
    def test_poll_delivery_status_driver_found(self, mock_get):
        """Test polling delivery status when driver is found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'delivery_id': 'uber_delivery_123',
            'status': 'driver_found',
            'driver': {
                'name': 'John Driver',
                'phone_number': '+5511999999999',
                'vehicle': {
                    'make': 'Toyota',
                    'model': 'Corolla'
                },
                'location': {
                    'latitude': -23.5505,
                    'longitude': -46.6333
                }
            }
        }
        mock_get.return_value = mock_response

        client = UberDeliveryClient(self.store)
        result = client.poll_delivery_status('uber_delivery_123')

        assert result is not None
        assert result['status'] == 'driver_found'
        assert 'driver' in result
        assert result['driver']['name'] == 'John Driver'
        mock_get.assert_called_once()

    @patch('orders.services.uber_delivery.requests.get')
    def test_poll_delivery_status_searching(self, mock_get):
        """Test polling delivery status while driver search is in progress."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'delivery_id': 'uber_delivery_123',
            'status': 'searching_for_driver',
            'estimated_time': 300
        }
        mock_get.return_value = mock_response

        client = UberDeliveryClient(self.store)
        result = client.poll_delivery_status('uber_delivery_123')

        assert result is not None
        assert result['status'] == 'searching_for_driver'
        assert result['estimated_time'] == 300

    @patch('orders.services.uber_delivery.requests.delete')
    def test_cancel_delivery_request_success(self, mock_delete):
        """Test successful delivery cancellation."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        client = UberDeliveryClient(self.store)
        result = client.cancel_delivery_request('uber_delivery_123')

        assert result is True
        mock_delete.assert_called_once()


@pytest.mark.django_db
class TestOrderDeliveryAPI:
    """Tests for Order Delivery API endpoints."""

    def setup_method(self):
        """Setup test data and client."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            owner=self.user,
            whatsapp='+5511999999999',
            uber_client_id='test_client_id',
            uber_client_secret='test_client_secret',
            uber_restaurant_id='test_restaurant_id'
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_phone='+5511988888888',
            customer_name='Test Customer',
            status=OrderStatus.CONFIRMED,
            total_price=50.00,
            delivery_address='Rua Test, 123, São Paulo, SP'
        )
        self.client.force_authenticate(user=self.user)

    @patch('orders.services.uber_delivery.UberDeliveryClient.create_delivery_request')
    def test_create_delivery_request_endpoint_success(self, mock_uber_request):
        """Test POST /api/orders/{order_id}/delivery endpoint success."""
        mock_uber_request.return_value = {
            'delivery_id': 'uber_delivery_123',
            'status': 'scheduled',
            'pickup': {'location': {'address': 'Store Address'}},
            'dropoff': {'location': {'address': 'Customer Address'}}
        }

        url = f'/api/orders/{self.order.id}/delivery/'
        data = {
            'delivery_type': 'uber',
            'pickup_address': 'Rua Store, 100, São Paulo, SP'
        }

        response = self.client.post(url, data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['delivery_id'] == 'uber_delivery_123'
        assert response.data['status'] == 'scheduled'

    def test_create_delivery_request_invalid_state(self):
        """Test delivery request creation with invalid order state."""
        # Update order to invalid state for delivery
        self.order.status = OrderStatus.CANCELLED
        self.order.save()

        url = f'/api/orders/{self.order.id}/delivery/'
        data = {
            'delivery_type': 'uber',
            'pickup_address': 'Rua Store, 100, São Paulo, SP'
        }

        response = self.client.post(url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data or 'detail' in response.data

    @patch('orders.services.uber_delivery.UberDeliveryClient.poll_delivery_status')
    def test_poll_delivery_status_endpoint_driver_found(self, mock_poll):
        """Test GET /api/orders/{order_id}/delivery/status endpoint."""
        # First create a delivery
        self.order.uber_delivery_id = 'uber_delivery_123'
        self.order.save()

        mock_poll.return_value = {
            'delivery_id': 'uber_delivery_123',
            'status': 'driver_found',
            'driver': {
                'name': 'John Driver',
                'phone_number': '+5511999999999'
            }
        }

        url = f'/api/orders/{self.order.id}/delivery/status/'
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'driver_found'
        assert response.data['driver']['name'] == 'John Driver'

    @patch('orders.services.uber_delivery.UberDeliveryClient.cancel_delivery_request')
    def test_cancel_delivery_request_endpoint(self, mock_cancel):
        """Test DELETE /api/orders/{order_id}/delivery endpoint."""
        # First create a delivery
        self.order.uber_delivery_id = 'uber_delivery_123'
        self.order.save()

        mock_cancel.return_value = True

        url = f'/api/orders/{self.order.id}/delivery/'
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_cancel.assert_called_once_with('uber_delivery_123')
