"""
Tests that ensure the new `/api/v1/stores/` endpoints (catalog and maps) are wired correctly.
We exercise the storefront and HERE Maps routes against the unified API.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.stores.models import Store

User = get_user_model()


class StoreCatalogAndMapsAPITestCase(TestCase):
    """Smoke tests for the unified store catalog and maps endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='mapstest',
            email='maps@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.store = Store.objects.create(
            name='Pastita Test Store',
            slug='pastita',
            description='Test store for API coverage',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
            currency='BRL',
            timezone='America/Sao_Paulo',
            latitude=Decimal('-10.185260'),
            longitude=Decimal('-48.303478'),
        )

    def test_store_catalog_endpoint_is_available(self):
        """The store catalog endpoint should still respond 200 even when empty."""
        response = self.client.get(f'/api/v1/stores/s/{self.store.slug}/catalog/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.stores.api.maps_views.here_maps_service')
    def test_maps_geocode_endpoint(self, mock_maps_service):
        mock_maps_service.geocode.return_value = {
            'lat': -10.185,
            'lng': -48.303,
            'formatted_address': 'Palmas, TO'
        }

        response = self.client.get('/api/v1/stores/maps/geocode/', {'address': 'Palmas, TO'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['formatted_address'], 'Palmas, TO')

    @patch('apps.stores.api.maps_views.here_maps_service')
    def test_maps_reverse_geocode_endpoint(self, mock_maps_service):
        mock_maps_service.reverse_geocode.return_value = {
            'formatted_address': 'Palmas, TO',
            'city': 'Palmas',
            'state': 'TO',
        }

        response = self.client.get('/api/v1/stores/maps/reverse-geocode/', {'lat': '-10.185', 'lng': '-48.303'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['city'], 'Palmas')

    @patch('apps.stores.api.maps_views.here_maps_service')
    def test_maps_autosuggest_endpoint(self, mock_maps_service):
        mock_maps_service.autosuggest.return_value = [
            {'title': 'Palmas, TO', 'lat': -10.185, 'lng': -48.303}
        ]

        response = self.client.get('/api/v1/stores/maps/autosuggest/', {'q': 'Palmas'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['suggestions'])

    @patch('apps.stores.api.maps_views.here_maps_service')
    def test_store_delivery_zones_endpoint(self, mock_maps_service):
        mock_maps_service.get_delivery_zones_isolines.return_value = [
            {'minutes': 10, 'polygons': []}
        ]

        response = self.client.get(f'/api/v1/stores/s/{self.store.slug}/delivery-zones/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('zones', response.data)

    @patch('apps.stores.api.maps_views.here_maps_service')
    @patch('apps.stores.api.maps_views.CheckoutService.calculate_delivery_fee')
    def test_validate_delivery_endpoint(self, mock_calc_fee, mock_maps_service):
        mock_maps_service.validate_delivery_address.return_value = {
            'is_valid': True,
            'distance_km': 2.5,
            'duration_minutes': 7.0,
            'polyline': '',
        }
        mock_calc_fee.return_value = {
            'fee': Decimal('8.00'),
            'zone_name': 'Centro',
            'estimated_minutes': 25,
        }

        payload = {
            'lat': '-10.1847',
            'lng': '-48.3337',
        }
        response = self.client.post(f'/api/v1/stores/s/{self.store.slug}/validate-delivery/', payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('delivery_fee', response.data)
        self.assertEqual(
            Decimal(str(response.data['delivery_fee'])),
            Decimal('8.00')
        )
