import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from apps.orders.models import StoreOrder
from apps.stores.models import Store, StoreCustomer
from apps.orders.services.uber_delivery import UberDeliveryClient


@pytest.mark.django_db
class TestUberDeliveryClient(TestCase):
    """Tests for UberDeliveryClient service."""

    def setUp(self):
        self.client = UberDeliveryClient()

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_create_delivery_request_success(self, mock_post):
        """Test creating a delivery request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'delivery_request_id': 'req_123',
            'status': 'pending',
        }
        mock_post.return_value = mock_response

        result = self.client.create_delivery_request(
            pickup_address='123 Store St',
            dropoff_address='456 Customer Ave',
            customer_phone='+5511999999999',
            order_id=1,
        )

        assert result['delivery_request_id'] == 'req_123'
        assert result['status'] == 'pending'
        mock_post.assert_called_once()

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_create_delivery_request_failure(self, mock_post):
        """Test create fails with API error."""
        mock_post.side_effect = Exception("API Error")

        with pytest.raises(Exception):
            self.client.create_delivery_request(
                pickup_address='123 Store St',
                dropoff_address='456 Customer Ave',
                customer_phone='+5511999999999',
                order_id=1,
            )

    @patch('apps.orders.services.uber_delivery.requests.get')
    def test_poll_delivery_status_driver_found(self, mock_get):
        """Test polling when driver is found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'accepted',
            'driver': {
                'id': 'driver_456',
                'name': 'João Silva',
                'phone': '+5511988888888',
                'vehicle': {'display_name': 'Honda Civic Branco - ABC 1234'},
                'rating': 4.8,
                'eta': {'estimated_minutes_to_pickup': 12},
            },
            'special_instructions': 'Ring doorbell twice',
        }
        mock_get.return_value = mock_response

        result = self.client.poll_delivery_status('req_123')

        assert result['status'] == 'accepted'
        assert result['driver']['name'] == 'João Silva'
        assert result['driver']['eta_minutes'] == 12

    @patch('apps.orders.services.uber_delivery.requests.get')
    def test_poll_delivery_status_searching(self, mock_get):
        """Test polling when no driver assigned yet."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'pending',
        }
        mock_get.return_value = mock_response

        result = self.client.poll_delivery_status('req_123')

        assert result['status'] == 'pending'
        assert 'driver' not in result

    @patch('apps.orders.services.uber_delivery.requests.post')
    def test_cancel_delivery_request_success(self, mock_post):
        """Test cancelling a delivery request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'cancelled'}
        mock_post.return_value = mock_response

        result = self.client.cancel_delivery_request('req_123')

        assert result['status'] == 'cancelled'
        mock_post.assert_called_once()


@pytest.mark.django_db
class TestOrderDeliveryAPI(TestCase):
    """Tests for order delivery API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='owner@test.com',
            email='owner@test.com',
            password='testpass123'
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Ce Saladas',
            slug='ce-saladas',
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            order_number='ORD001',
            status='confirmado',
            subtotal=99.90,
            total=99.90,
        )

    @patch('apps.orders.services.uber_delivery.UberDeliveryClient.create_delivery_request')
    def test_create_delivery_request_endpoint_success(self, mock_uber):
        """Test POST /api/v1/stores/{slug}/orders/{id}/create-delivery-request"""
        mock_uber.return_value = {'delivery_request_id': 'req_123', 'status': 'pending'}

        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/create-delivery-request/'
        response = self.client.post(url)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data['delivery_request_id'] == 'req_123'

        self.order.refresh_from_db()
        assert self.order.uber_delivery_request_id == 'req_123'
        assert self.order.delivery_provider == 'uber'

    def test_create_delivery_request_invalid_state(self):
        """Test cannot create delivery for cancelled order."""
        self.order.status = 'cancelado'
        self.order.save()

        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/create-delivery-request/'
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'confirmado' in response.data['detail'].lower()

    @patch('apps.orders.services.uber_delivery.UberDeliveryClient.poll_delivery_status')
    def test_poll_delivery_status_endpoint_driver_found(self, mock_poll):
        """Test GET /api/v1/stores/{slug}/orders/{id}/delivery-request-status/"""
        self.order.uber_delivery_request_id = 'req_123'
        self.order.save()

        mock_poll.return_value = {
            'status': 'accepted',
            'driver': {
                'name': 'João Silva',
                'phone': '+5511999999999',
                'vehicle': 'Honda Civic',
                'eta_minutes': 12,
                'pickup_instructions': 'Ring doorbell',
            }
        }

        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/delivery-request-status/'
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'accepted'
        assert response.data['driver']['name'] == 'João Silva'

    @patch('apps.orders.services.uber_delivery.UberDeliveryClient.cancel_delivery_request')
    def test_cancel_delivery_request_endpoint(self, mock_cancel):
        """Test DELETE /api/v1/stores/{slug}/orders/{id}/delivery-request/"""
        self.order.uber_delivery_request_id = 'req_123'
        self.order.uber_driver_name = 'João Silva'
        self.order.save()

        mock_cancel.return_value = {'status': 'cancelled'}

        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/delivery-request/'
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'cancelled'

        self.order.refresh_from_db()
        assert self.order.uber_delivery_request_id is None
        assert self.order.uber_driver_name == ''
