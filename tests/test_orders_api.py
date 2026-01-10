"""
Tests for Orders API endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class OrdersAPITestCase(TestCase):
    """Tests for Orders API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_list_orders(self):
        """Test listing orders."""
        response = self.client.get('/api/v1/orders/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_get_orders_history(self):
        """Test getting orders history."""
        response = self.client.get('/api/v1/orders/history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_get_order_stats(self):
        """Test getting order statistics."""
        response = self.client.get('/api/v1/orders/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PaymentsAPITestCase(TestCase):
    """Tests for Payments API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_list_payments(self):
        """Test listing payments."""
        response = self.client.get('/api/v1/payments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_get_payment_stats(self):
        """Test getting payment statistics."""
        response = self.client.get('/api/v1/payments/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
