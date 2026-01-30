"""
HERE Maps Service - Unified location services for all stores.
Provides geocoding, routing, distance calculation, and isoline generation.

Cache Strategy:
- Routes: 24 hours (routes don't change frequently)
- Geocoding: 24 hours (addresses are stable)
- Reverse Geocoding: 24 hours
- Isolines: 6 hours (delivery zones)
- Autosuggest: No cache (real-time suggestions)
"""
import logging
import hashlib
import math
import requests
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# HERE Maps API Key (must be provided via environment/settings)
HERE_API_KEY = getattr(settings, 'HERE_API_KEY', '') or ''

# API Endpoints
HERE_GEOCODE_URL = "https://geocode.search.hereapi.com/v1/geocode"
HERE_REVERSE_GEOCODE_URL = "https://revgeocode.search.hereapi.com/v1/revgeocode"
HERE_ROUTING_URL = "https://router.hereapi.com/v8/routes"
HERE_ISOLINE_URL = "https://isoline.router.hereapi.com/v8/isolines"
HERE_AUTOSUGGEST_URL = "https://autosuggest.search.hereapi.com/v1/autosuggest"

# Cache TTLs (in seconds)
CACHE_TTL_ROUTE = 86400  # 24 hours - routes are stable
CACHE_TTL_GEOCODE = 86400  # 24 hours - addresses don't change
CACHE_TTL_ISOLINE = 21600  # 6 hours - delivery zones
CACHE_TTL_DEFAULT = 3600  # 1 hour - fallback


def _round_coords(lat: float, lng: float, precision: int = 4) -> Tuple[float, float]:
    """Round coordinates to reduce cache key variations."""
    return (round(lat, precision), round(lng, precision))


def _haversine_km(origin: Tuple[float, float], destination: Tuple[float, float]) -> float:
    """Calculate straight-line distance between two points in km."""
    lat1, lon1 = origin
    lat2, lon2 = destination
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _make_cache_key(prefix: str, *args) -> str:
    """Create a consistent cache key."""
    key_data = f"{prefix}:{':'.join(str(a) for a in args)}"
    return hashlib.md5(key_data.encode()).hexdigest()[:32]


class HereMapsService:
    """Service for HERE Maps API integration."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or HERE_API_KEY
    
    def geocode(self, address: str, country: str = "BRA") -> Optional[Dict]:
        """
        Convert address to coordinates.
        
        Args:
            address: Full address string
            country: ISO country code (default: BRA)
        
        Returns:
            Dict with lat, lng, formatted_address, or None if not found
        """
        # Normalize address for better cache hits
        normalized_address = address.strip().lower()
        cache_key = _make_cache_key("geocode", normalized_address, country)
        
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Geocode cache hit for: {address[:50]}")
            return cached
        
        try:
            response = requests.get(
                HERE_GEOCODE_URL,
                params={
                    'q': address,
                    'in': f'countryCode:{country}',
                    'apiKey': self.api_key,
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('items'):
                item = data['items'][0]
                position = item.get('position', {})
                result = {
                    'lat': position.get('lat'),
                    'lng': position.get('lng'),
                    'formatted_address': item.get('title', ''),
                    'address': item.get('address', {}),
                    'place_id': item.get('id'),
                }
                cache.set(cache_key, result, CACHE_TTL_GEOCODE)
                return result
            
            return None
        
        except Exception as e:
            logger.error(f"Geocode error: {e}")
            return None
    
    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        """
        Convert coordinates to address.
        
        Args:
            lat: Latitude
            lng: Longitude
        
        Returns:
            Dict with address details, or None if not found
        """
        # Round coordinates to reduce cache variations (4 decimal places = ~11m precision)
        rounded_lat, rounded_lng = _round_coords(lat, lng, 4)
        cache_key = _make_cache_key("revgeo", rounded_lat, rounded_lng)
        
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Reverse geocode cache hit for: {lat},{lng}")
            return cached
        
        try:
            response = requests.get(
                HERE_REVERSE_GEOCODE_URL,
                params={
                    'at': f'{lat},{lng}',
                    'apiKey': self.api_key,
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('items'):
                item = data['items'][0]
                address = item.get('address', {})
                result = {
                    'formatted_address': item.get('title', ''),
                    'street': address.get('street', ''),
                    'house_number': address.get('houseNumber', ''),
                    'neighborhood': address.get('district', ''),
                    'city': address.get('city', ''),
                    'state': address.get('state', ''),
                    'state_code': address.get('stateCode', ''),
                    'zip_code': address.get('postalCode', ''),
                    'country': address.get('countryName', ''),
                    'country_code': address.get('countryCode', ''),
                }
                cache.set(cache_key, result, CACHE_TTL_GEOCODE)
                return result
            
            return None
        
        except Exception as e:
            logger.error(f"Reverse geocode error: {e}")
            return None
    
    def calculate_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        transport_mode: str = "car"
    ) -> Optional[Dict]:
        """
        Calculate route between two points.
        
        Args:
            origin: (lat, lng) tuple
            destination: (lat, lng) tuple
            transport_mode: car, pedestrian, bicycle, truck
        
        Returns:
            Dict with distance_km, duration_minutes, polyline
        """
        # Round coordinates to 4 decimal places for cache efficiency
        origin_rounded = _round_coords(origin[0], origin[1], 4)
        dest_rounded = _round_coords(destination[0], destination[1], 4)
        cache_key = _make_cache_key("route", origin_rounded, dest_rounded, transport_mode)
        
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Route cache hit: {origin} -> {destination}")
            return cached
        
        def fallback_route() -> Dict:
            distance_km = round(_haversine_km(origin, destination), 2)
            avg_speed_kmh = 30.0
            duration_minutes = round((distance_km / avg_speed_kmh) * 60, 1) if avg_speed_kmh > 0 else 0
            return {
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'polyline': '',
                'departure': {},
                'arrival': {},
                'fallback': True,
            }

        if not self.api_key:
            logger.warning("HERE_API_KEY not configured, using fallback route estimation")
            return fallback_route()

        try:
            logger.info(f"Calculating route: {origin} -> {destination}")
            response = requests.get(
                HERE_ROUTING_URL,
                params={
                    'origin': f'{origin[0]},{origin[1]}',
                    'destination': f'{destination[0]},{destination[1]}',
                    'transportMode': transport_mode,
                    'return': 'summary,polyline',
                    'apiKey': self.api_key,
                },
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"HERE API error: {response.status_code} - {response.text}")
                return fallback_route()
            
            data = response.json()
            
            if data.get('routes'):
                route = data['routes'][0]
                section = route['sections'][0]
                summary = section.get('summary', {})
                
                result = {
                    'distance_km': round(summary.get('length', 0) / 1000, 2),
                    'duration_minutes': round(summary.get('duration', 0) / 60, 1),
                    'polyline': section.get('polyline', ''),
                    'departure': section.get('departure', {}),
                    'arrival': section.get('arrival', {}),
                }
                # Cache routes for 24 hours - they don't change frequently
                cache.set(cache_key, result, CACHE_TTL_ROUTE)
                logger.info(f"Route calculated: {result['distance_km']} km, {result['duration_minutes']} min")
                return result
            
            logger.warning(f"No routes found in response: {data}")
            return fallback_route()
        
        except Exception as e:
            logger.error(f"Route calculation error: {e}", exc_info=True)
            return fallback_route()
    
    def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float]
    ) -> Optional[Decimal]:
        """
        Calculate distance between two points in kilometers.
        
        Args:
            origin: (lat, lng) tuple
            destination: (lat, lng) tuple
        
        Returns:
            Distance in kilometers as Decimal
        """
        route = self.calculate_route(origin, destination)
        if route:
            return Decimal(str(route['distance_km']))
        return None
    
    def get_isoline(
        self,
        center: Tuple[float, float],
        range_type: str = "time",
        range_value: int = 900,
        transport_mode: str = "car"
    ) -> Optional[Dict]:
        """
        Generate isoline (reachability polygon) from a center point.
        
        Args:
            center: (lat, lng) tuple - center point
            range_type: "time" (seconds) or "distance" (meters)
            range_value: Range value (default: 900 seconds = 15 minutes)
            transport_mode: car, pedestrian, bicycle, truck
        
        Returns:
            Dict with polygon coordinates and metadata
        """
        # Round center coordinates for cache efficiency
        center_rounded = _round_coords(center[0], center[1], 3)  # 3 decimals for isolines
        cache_key = _make_cache_key("isoline", center_rounded, range_type, range_value, transport_mode)
        
        cached = cache.get(cache_key)
        if cached:
            logger.debug(f"Isoline cache hit: {center}")
            return cached
        
        try:
            params = {
                'origin': f'{center[0]},{center[1]}',
                'transportMode': transport_mode,
                'apiKey': self.api_key,
            }
            
            if range_type == "time":
                params['range[type]'] = 'time'
                params['range[values]'] = str(range_value)
            else:
                params['range[type]'] = 'distance'
                params['range[values]'] = str(range_value)
            
            response = requests.get(
                HERE_ISOLINE_URL,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('isolines'):
                isoline = data['isolines'][0]
                polygons = isoline.get('polygons', [])
                
                result = {
                    'range_type': range_type,
                    'range_value': range_value,
                    'transport_mode': transport_mode,
                    'polygons': polygons,
                    'center': {'lat': center[0], 'lng': center[1]},
                }
                # Cache isolines for 6 hours
                cache.set(cache_key, result, CACHE_TTL_ISOLINE)
                return result
            
            return None
        
        except Exception as e:
            logger.error(f"Isoline generation error: {e}")
            return None
    
    def get_delivery_zones_isolines(
        self,
        center: Tuple[float, float],
        time_ranges: List[int] = None
    ) -> List[Dict]:
        """
        Generate multiple isolines for delivery zones.
        
        Args:
            center: (lat, lng) tuple - store location
            time_ranges: List of time ranges in minutes (default: [10, 20, 30, 45])
        
        Returns:
            List of isoline dicts for each time range
        """
        if time_ranges is None:
            time_ranges = [10, 20, 30, 45]
        
        zones = []
        for minutes in time_ranges:
            isoline = self.get_isoline(
                center=center,
                range_type="time",
                range_value=minutes * 60,  # Convert to seconds
                transport_mode="car"
            )
            if isoline:
                isoline['minutes'] = minutes
                zones.append(isoline)
        
        return zones
    
    def autosuggest(
        self,
        query: str,
        center: Tuple[float, float] = None,
        country: str = "BRA",
        limit: int = 5
    ) -> List[Dict]:
        """
        Get address suggestions for autocomplete.
        
        Args:
            query: Search query
            center: (lat, lng) tuple for biasing results (required by HERE API)
            country: ISO country code
            limit: Maximum number of results
        
        Returns:
            List of suggestion dicts
        """
        try:
            # HERE Autosuggest API requires 'at' parameter
            # Use center if provided, otherwise use Brazil center (Brasília)
            if center:
                at_param = f'{center[0]},{center[1]}'
            else:
                # Default to Brasília, Brazil as center point
                at_param = '-15.7801,-47.9292'
            
            params = {
                'q': query,
                'at': at_param,
                'in': f'countryCode:{country}',
                'limit': limit,
                'apiKey': self.api_key,
            }
            
            response = requests.get(
                HERE_AUTOSUGGEST_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            suggestions = []
            for item in data.get('items', []):
                position = item.get('position', {})
                suggestions.append({
                    'title': item.get('title', ''),
                    'address': item.get('address', {}),
                    'lat': position.get('lat'),
                    'lng': position.get('lng'),
                    'place_id': item.get('id'),
                    'result_type': item.get('resultType', ''),
                })
            
            return suggestions
        
        except Exception as e:
            logger.error(f"Autosuggest error: {e}")
            return []
    
    def validate_delivery_address(
        self,
        store_location: Tuple[float, float],
        delivery_address: Tuple[float, float],
        max_distance_km: float = 20.0,
        max_time_minutes: float = 45.0
    ) -> Dict:
        """
        Validate if a delivery address is within service area.
        
        Args:
            store_location: (lat, lng) of store
            delivery_address: (lat, lng) of delivery address
            max_distance_km: Maximum delivery distance
            max_time_minutes: Maximum delivery time
        
        Returns:
            Dict with is_valid, distance_km, duration_minutes, message
        """
        route = self.calculate_route(store_location, delivery_address)
        
        if not route:
            return {
                'is_valid': False,
                'message': 'Não foi possível calcular a rota',
            }
        
        distance_km = route['distance_km']
        duration_minutes = route['duration_minutes']
        polyline = route.get('polyline')
        
        if distance_km > max_distance_km:
            return {
                'is_valid': False,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'polyline': polyline,  # Always include polyline for map display
                'message': f'Endereço fora da área de entrega (máx: {max_distance_km}km)',
            }
        
        if duration_minutes > max_time_minutes:
            return {
                'is_valid': False,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'polyline': polyline,  # Always include polyline for map display
                'message': f'Tempo de entrega muito longo (máx: {max_time_minutes}min)',
            }
        
        return {
            'is_valid': True,
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'polyline': polyline,
            'message': 'Endereço válido para entrega',
        }


# Singleton instance
here_maps_service = HereMapsService()
