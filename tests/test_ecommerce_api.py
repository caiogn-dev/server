"""
Tests for E-commerce API endpoints.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

User = get_user_model()


class ProductAPITestCase(TestCase):
    """Tests for Product API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_list_products(self):
        """Test listing products."""
        response = self.client.get('/api/v1/products/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_products_with_category_filter(self):
        """Test listing products with category filter."""
        response = self.client.get('/api/v1/products/', {'category': 'test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_get_product_categories(self):
        """Test getting product categories."""
        response = self.client.get('/api/v1/products/categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class CartAPITestCase(TestCase):
    """Tests for Cart API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_get_cart(self):
        """Test getting cart."""
        response = self.client.get('/api/v1/cart/list/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_clear_cart(self):
        """Test clearing cart."""
        response = self.client.post('/api/v1/cart/clear/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class DeliveryAPITestCase(TestCase):
    """Tests for Delivery API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_list_delivery_zones(self):
        """Test listing delivery zones."""
        response = self.client.get('/api/v1/delivery/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_calculate_delivery(self):
        """Test calculating delivery fee."""
        response = self.client.post('/api/v1/delivery/calculate/', {
            'zip_code': '77020170',
            'address': 'Test Address',
            'city': 'Palmas',
            'state': 'TO'
        })
        # Should return 200 even if no zones match
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])


class CouponAPITestCase(TestCase):
    """Tests for Coupon API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_validate_invalid_coupon(self):
        """Test validating an invalid coupon."""
        response = self.client.post('/api/v1/coupons/validate/', {
            'code': 'INVALID123',
            'total': 100.00
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GeocodingAPITestCase(TestCase):
    """Tests for Geocoding API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_search_address(self):
        """Test searching for an address."""
        response = self.client.post('/api/v1/ecommerce/geocoding/search/', {
            'query': 'Palmas, TO, Brasil'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_reverse_geocode(self):
        """Test reverse geocoding."""
        response = self.client.post('/api/v1/ecommerce/geocoding/reverse/', {
            'latitude': -10.1847,
            'longitude': -48.3337
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_get_suggestions(self):
        """Test getting address suggestions."""
        response = self.client.get('/api/v1/ecommerce/geocoding/suggestions/', {
            'query': 'Palmas'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_lookup_cep(self):
        """Test CEP lookup."""
        response = self.client.get('/api/v1/ecommerce/geocoding/cep/77020170/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AuthAPITestCase(TestCase):
    """Tests for Authentication API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_login(self):
        """Test user login."""
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_get_profile(self):
        """Test getting user profile."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/v1/auth/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_logout(self):
        """Test user logout."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/v1/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
