"""
HERE Maps API Views - Location services for stores.
"""
import logging
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from apps.stores.models import Store
from apps.stores.services.here_maps_service import here_maps_service

logger = logging.getLogger(__name__)


class StoreGeocodeView(APIView):
    """Geocode an address."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """
        GET /api/v1/stores/maps/geocode/?address=...
        """
        address = request.query_params.get('address')
        if not address:
            return Response(
                {'error': 'address parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = here_maps_service.geocode(address)
        if result:
            return Response(result)
        return Response(
            {'error': 'Address not found'},
            status=status.HTTP_404_NOT_FOUND
        )


class StoreReverseGeocodeView(APIView):
    """Reverse geocode coordinates to address."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """
        GET /api/v1/stores/maps/reverse-geocode/?lat=...&lng=...
        """
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        
        if not lat or not lng:
            return Response(
                {'error': 'lat and lng parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = here_maps_service.reverse_geocode(float(lat), float(lng))
            if result:
                return Response(result)
            return Response(
                {'error': 'Location not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {'error': 'Invalid lat/lng values'},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreRouteView(APIView):
    """Calculate route between two points."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """
        GET /api/v1/stores/s/{store_slug}/route/?dest_lat=...&dest_lng=...
        Calculate route from store to destination.
        """
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        dest_lat = request.query_params.get('dest_lat')
        dest_lng = request.query_params.get('dest_lng')
        
        if not dest_lat or not dest_lng:
            return Response(
                {'error': 'dest_lat and dest_lng parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not store.latitude or not store.longitude:
            return Response(
                {'error': 'Store location not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            origin = (float(store.latitude), float(store.longitude))
            destination = (float(dest_lat), float(dest_lng))
            
            result = here_maps_service.calculate_route(origin, destination)
            if result:
                return Response({
                    'store': {
                        'name': store.name,
                        'lat': float(store.latitude),
                        'lng': float(store.longitude),
                    },
                    'destination': {
                        'lat': float(dest_lat),
                        'lng': float(dest_lng),
                    },
                    **result
                })
            return Response(
                {'error': 'Could not calculate route'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError:
            return Response(
                {'error': 'Invalid coordinate values'},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreValidateDeliveryView(APIView):
    """Validate if delivery address is within service area."""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, store_slug):
        """
        POST /api/v1/stores/s/{store_slug}/validate-delivery/
        
        Body:
        {
            "lat": -10.1847,
            "lng": -48.3337
        }
        or
        {
            "address": "Rua Example, 123, Palmas, TO"
        }
        """
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        if not store.latitude or not store.longitude:
            return Response(
                {'error': 'Store location not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get delivery coordinates
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        
        if not lat or not lng:
            # Try to geocode address
            address = request.data.get('address')
            if address:
                geocoded = here_maps_service.geocode(address)
                if geocoded:
                    lat = geocoded['lat']
                    lng = geocoded['lng']
                else:
                    return Response(
                        {'error': 'Could not geocode address'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {'error': 'lat/lng or address is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            store_location = (float(store.latitude), float(store.longitude))
            delivery_location = (float(lat), float(lng))
            
            # Get max distance from store settings or use default
            max_distance = float(store.metadata.get('max_delivery_distance_km', 20))
            max_time = float(store.metadata.get('max_delivery_time_minutes', 45))
            
            result = here_maps_service.validate_delivery_address(
                store_location=store_location,
                delivery_address=delivery_location,
                max_distance_km=max_distance,
                max_time_minutes=max_time
            )
            
            # Add delivery fee calculation
            if result['is_valid']:
                from apps.stores.services.checkout_service import CheckoutService
                fee_info = CheckoutService.calculate_delivery_fee(
                    store,
                    distance_km=Decimal(str(result['distance_km']))
                )
                result['delivery_fee'] = fee_info['fee']
                result['delivery_zone'] = fee_info.get('zone_name')
                result['estimated_minutes'] = fee_info.get('estimated_minutes')
            
            return Response(result)
        
        except ValueError:
            return Response(
                {'error': 'Invalid coordinate values'},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreDeliveryZonesView(APIView):
    """Get delivery zones as isolines."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """
        GET /api/v1/stores/s/{store_slug}/delivery-zones/
        Returns isoline polygons for delivery zones.
        """
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        if not store.latitude or not store.longitude:
            return Response(
                {'error': 'Store location not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        center = (float(store.latitude), float(store.longitude))
        
        # Get time ranges from query params or use defaults
        time_ranges_param = request.query_params.get('time_ranges')
        if time_ranges_param:
            try:
                time_ranges = [int(x) for x in time_ranges_param.split(',')]
            except ValueError:
                time_ranges = [10, 20, 30, 45]
        else:
            time_ranges = [10, 20, 30, 45]
        
        zones = here_maps_service.get_delivery_zones_isolines(center, time_ranges)
        
        return Response({
            'store': {
                'name': store.name,
                'lat': float(store.latitude),
                'lng': float(store.longitude),
            },
            'zones': zones,
        })


class StoreAutosuggestView(APIView):
    """Address autocomplete suggestions."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug=None):
        """
        GET /api/v1/stores/s/{store_slug}/autosuggest/?q=...
        or
        GET /api/v1/stores/maps/autosuggest/?q=...
        """
        query = request.query_params.get('q')
        if not query or len(query) < 3:
            return Response({'suggestions': []})
        
        # Get center point for biasing results
        center = None
        if store_slug:
            store = get_object_or_404(Store, slug=store_slug, status='active')
            if store.latitude and store.longitude:
                center = (float(store.latitude), float(store.longitude))
        
        limit = int(request.query_params.get('limit', 5))
        suggestions = here_maps_service.autosuggest(query, center=center, limit=limit)
        
        return Response({'suggestions': suggestions})
