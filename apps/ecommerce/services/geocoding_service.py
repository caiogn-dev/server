# -*- coding: utf-8 -*-
"""
Geocoding Service - OpenStreetMap-based geocoding, reverse geocoding, and routing.

Uses:
- Nominatim for geocoding and reverse geocoding
- OSRM for route calculation
- ViaCEP for Brazilian zip code lookup
"""
import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class GeoLocation:
    """Represents a geographic location."""
    latitude: Decimal
    longitude: Decimal
    display_name: str = ''
    address: str = ''
    city: str = ''
    state: str = ''
    country: str = ''
    zip_code: str = ''
    place_id: Optional[int] = None
    osm_type: str = ''
    osm_id: Optional[int] = None
    importance: float = 0.0
    bounding_box: Optional[List[float]] = None


@dataclass
class RouteInfo:
    """Represents route information between two points."""
    distance_km: Decimal
    duration_minutes: int
    geometry: Optional[str] = None  # Encoded polyline
    steps: Optional[List[Dict[str, Any]]] = None
    summary: str = ''


@dataclass
class SearchSuggestion:
    """Represents an address search suggestion."""
    display_name: str
    latitude: Decimal
    longitude: Decimal
    place_id: int
    osm_type: str
    osm_id: int
    address_type: str = ''
    importance: float = 0.0


class GeocodingService:
    """
    Comprehensive geocoding service using OpenStreetMap services.
    
    Features:
    - Forward geocoding (address to coordinates)
    - Reverse geocoding (coordinates to address)
    - Address autocomplete/search suggestions
    - Route calculation with turn-by-turn directions
    - Brazilian CEP (zip code) lookup
    """
    
    def __init__(self):
        self.nominatim_url = getattr(
            settings, 'NOMINATIM_URL', 
            'https://nominatim.openstreetmap.org'
        )
        self.osrm_url = getattr(
            settings, 'OSRM_URL', 
            'https://router.project-osrm.org'
        )
        self.viacep_url = getattr(
            settings, 'VIACEP_URL', 
            'https://viacep.com.br/ws/{zip}/json/'
        )
        self.user_agent = getattr(
            settings, 'GEOCODE_USER_AGENT', 
            'pastita-platform/1.0 (contact@pastita.com.br)'
        )
        self.timeout = int(getattr(settings, 'GEOCODE_TIMEOUT', 10))
        self.cache_ttl = int(getattr(settings, 'GEOCODE_CACHE_TTL', 86400))  # 24 hours
    
    def _make_request(
        self, 
        url: str, 
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Optional[Any]:
        """Make HTTP request with error handling."""
        try:
            default_headers = {'User-Agent': self.user_agent}
            if headers:
                default_headers.update(headers)
            
            response = requests.get(
                url,
                params=params,
                headers=default_headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            
            logger.warning(
                "Request failed: %s - Status: %d", 
                url, response.status_code
            )
            return None
            
        except requests.RequestException as exc:
            logger.warning("Request error: %s - %s", url, exc)
            return None
    
    def geocode(
        self, 
        query: str,
        country_codes: Optional[List[str]] = None,
        limit: int = 5,
        bounded: bool = False,
        viewbox: Optional[Tuple[float, float, float, float]] = None
    ) -> List[GeoLocation]:
        """
        Forward geocoding - convert address to coordinates.
        
        Args:
            query: Address or place name to search
            country_codes: List of country codes to limit search (e.g., ['br'])
            limit: Maximum number of results
            bounded: If True, restrict results to viewbox
            viewbox: Bounding box (min_lon, min_lat, max_lon, max_lat)
        
        Returns:
            List of GeoLocation objects
        """
        cache_key = f"geocode:{query}:{country_codes}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        params = {
            'q': query,
            'format': 'json',
            'addressdetails': 1,
            'limit': limit,
        }
        
        if country_codes:
            params['countrycodes'] = ','.join(country_codes)
        
        if viewbox:
            params['viewbox'] = ','.join(map(str, viewbox))
            if bounded:
                params['bounded'] = 1
        
        data = self._make_request(f"{self.nominatim_url}/search", params)
        if not data:
            return []
        
        results = []
        for item in data:
            address = item.get('address', {})
            location = GeoLocation(
                latitude=Decimal(item['lat']),
                longitude=Decimal(item['lon']),
                display_name=item.get('display_name', ''),
                address=self._build_address_string(address),
                city=address.get('city') or address.get('town') or address.get('village', ''),
                state=address.get('state', ''),
                country=address.get('country', ''),
                zip_code=address.get('postcode', ''),
                place_id=item.get('place_id'),
                osm_type=item.get('osm_type', ''),
                osm_id=item.get('osm_id'),
                importance=item.get('importance', 0.0),
                bounding_box=[float(x) for x in item.get('boundingbox', [])]
            )
            results.append(location)
        
        cache.set(cache_key, results, self.cache_ttl)
        return results
    
    def reverse_geocode(
        self, 
        latitude: float, 
        longitude: float,
        zoom: int = 18
    ) -> Optional[GeoLocation]:
        """
        Reverse geocoding - convert coordinates to address.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            zoom: Level of detail (0-18, higher = more detail)
        
        Returns:
            GeoLocation object or None
        """
        cache_key = f"reverse:{latitude:.6f}:{longitude:.6f}:{zoom}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'addressdetails': 1,
            'zoom': zoom,
        }
        
        data = self._make_request(f"{self.nominatim_url}/reverse", params)
        if not data or 'error' in data:
            return None
        
        address = data.get('address', {})
        location = GeoLocation(
            latitude=Decimal(data['lat']),
            longitude=Decimal(data['lon']),
            display_name=data.get('display_name', ''),
            address=self._build_address_string(address),
            city=address.get('city') or address.get('town') or address.get('village', ''),
            state=address.get('state', ''),
            country=address.get('country', ''),
            zip_code=address.get('postcode', ''),
            place_id=data.get('place_id'),
            osm_type=data.get('osm_type', ''),
            osm_id=data.get('osm_id'),
        )
        
        cache.set(cache_key, location, self.cache_ttl)
        return location
    
    def search_suggestions(
        self, 
        query: str,
        country_codes: Optional[List[str]] = None,
        limit: int = 10,
        viewbox: Optional[Tuple[float, float, float, float]] = None
    ) -> List[SearchSuggestion]:
        """
        Get address autocomplete suggestions.
        
        Args:
            query: Partial address or place name
            country_codes: List of country codes to limit search
            limit: Maximum number of suggestions
            viewbox: Prefer results within this bounding box
        
        Returns:
            List of SearchSuggestion objects
        """
        if len(query) < 3:
            return []
        
        cache_key = f"suggest:{query}:{country_codes}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        params = {
            'q': query,
            'format': 'json',
            'addressdetails': 1,
            'limit': limit,
        }
        
        if country_codes:
            params['countrycodes'] = ','.join(country_codes)
        
        if viewbox:
            params['viewbox'] = ','.join(map(str, viewbox))
        
        data = self._make_request(f"{self.nominatim_url}/search", params)
        if not data:
            return []
        
        suggestions = []
        for item in data:
            suggestion = SearchSuggestion(
                display_name=item.get('display_name', ''),
                latitude=Decimal(item['lat']),
                longitude=Decimal(item['lon']),
                place_id=item.get('place_id', 0),
                osm_type=item.get('osm_type', ''),
                osm_id=item.get('osm_id', 0),
                address_type=item.get('type', ''),
                importance=item.get('importance', 0.0),
            )
            suggestions.append(suggestion)
        
        cache.set(cache_key, suggestions, 300)  # Cache for 5 minutes
        return suggestions
    
    def calculate_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        profile: str = 'driving',
        alternatives: bool = False,
        steps: bool = True,
        geometries: str = 'polyline6'
    ) -> Optional[RouteInfo]:
        """
        Calculate route between two points using OSRM.
        
        Args:
            origin: (latitude, longitude) of start point
            destination: (latitude, longitude) of end point
            profile: Routing profile ('driving', 'walking', 'cycling')
            alternatives: Whether to return alternative routes
            steps: Whether to include turn-by-turn directions
            geometries: Geometry format ('polyline', 'polyline6', 'geojson')
        
        Returns:
            RouteInfo object or None
        """
        origin_lat, origin_lon = origin
        dest_lat, dest_lon = destination
        
        # OSRM expects lon,lat order
        coords = f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        
        params = {
            'overview': 'full' if geometries else 'false',
            'geometries': geometries,
            'steps': 'true' if steps else 'false',
            'alternatives': 'true' if alternatives else 'false',
        }
        
        # Map profile names
        profile_map = {
            'driving': 'driving',
            'car': 'driving',
            'walking': 'foot',
            'foot': 'foot',
            'cycling': 'bike',
            'bike': 'bike',
        }
        osrm_profile = profile_map.get(profile, 'driving')
        
        url = f"{self.osrm_url}/route/v1/{osrm_profile}/{coords}"
        data = self._make_request(url, params)
        
        if not data or data.get('code') != 'Ok':
            # Fallback to haversine distance
            distance_km = self._haversine_distance(
                origin_lat, origin_lon, dest_lat, dest_lon
            )
            return RouteInfo(
                distance_km=distance_km,
                duration_minutes=int(distance_km * 2),  # Rough estimate
                summary='Direct distance (route unavailable)'
            )
        
        routes = data.get('routes', [])
        if not routes:
            return None
        
        route = routes[0]
        distance_km = Decimal(route['distance'] / 1000).quantize(Decimal('0.01'))
        duration_minutes = int(route['duration'] / 60)
        
        route_steps = None
        if steps and 'legs' in route:
            route_steps = []
            for leg in route['legs']:
                for step in leg.get('steps', []):
                    maneuver = step.get('maneuver', {})
                    route_steps.append({
                        'instruction': self._get_step_instruction(step, maneuver),
                        'distance': step.get('distance', 0),
                        'duration': step.get('duration', 0),
                        'name': step.get('name', ''),
                        'maneuver_type': maneuver.get('type', ''),
                        'maneuver_modifier': maneuver.get('modifier', ''),
                    })
        
        return RouteInfo(
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            geometry=route.get('geometry'),
            steps=route_steps,
            summary=route.get('legs', [{}])[0].get('summary', '')
        )
    
    def lookup_brazilian_cep(self, cep: str) -> Optional[Dict[str, str]]:
        """
        Look up Brazilian CEP (zip code) using ViaCEP.
        
        Args:
            cep: Brazilian CEP (8 digits)
        
        Returns:
            Dictionary with address components or None
        """
        clean_cep = ''.join(filter(str.isdigit, cep))[:8]
        if len(clean_cep) != 8:
            return None
        
        cache_key = f"viacep:{clean_cep}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        url = self.viacep_url.format(zip=clean_cep)
        data = self._make_request(url)
        
        if not data or data.get('erro'):
            return None
        
        result = {
            'cep': data.get('cep', ''),
            'address': data.get('logradouro', ''),
            'complement': data.get('complemento', ''),
            'neighborhood': data.get('bairro', ''),
            'city': data.get('localidade', ''),
            'state': data.get('uf', ''),
            'state_full': data.get('estado', ''),
            'ibge_code': data.get('ibge', ''),
            'ddd': data.get('ddd', ''),
        }
        
        cache.set(cache_key, result, self.cache_ttl)
        return result
    
    def geocode_brazilian_address(
        self, 
        cep: str,
        address: str = '',
        city: str = '',
        state: str = ''
    ) -> Optional[GeoLocation]:
        """
        Geocode a Brazilian address, using CEP lookup for better accuracy.
        
        Args:
            cep: Brazilian CEP
            address: Street address (optional, will be fetched from CEP if empty)
            city: City name (optional)
            state: State code (optional)
        
        Returns:
            GeoLocation object or None
        """
        # First, try to get address from CEP
        cep_data = self.lookup_brazilian_cep(cep)
        
        # Build search query
        query_parts = []
        
        if address:
            query_parts.append(address)
        elif cep_data and cep_data.get('address'):
            query_parts.append(cep_data['address'])
            if cep_data.get('neighborhood'):
                query_parts.append(cep_data['neighborhood'])
        
        if city:
            query_parts.append(city)
        elif cep_data and cep_data.get('city'):
            query_parts.append(cep_data['city'])
        
        if state:
            query_parts.append(state)
        elif cep_data and cep_data.get('state'):
            query_parts.append(cep_data['state'])
        
        query_parts.append('Brasil')
        
        query = ', '.join(filter(None, query_parts))
        
        # Try geocoding with full query
        results = self.geocode(query, country_codes=['br'], limit=1)
        if results:
            location = results[0]
            # Enrich with CEP data
            if cep_data:
                if not location.zip_code:
                    location.zip_code = cep_data.get('cep', '')
                if not location.city:
                    location.city = cep_data.get('city', '')
                if not location.state:
                    location.state = cep_data.get('state', '')
            return location
        
        # Fallback: try with just city and state
        if cep_data:
            fallback_query = f"{cep_data.get('city', '')}, {cep_data.get('state', '')}, Brasil"
            results = self.geocode(fallback_query, country_codes=['br'], limit=1)
            if results:
                location = results[0]
                location.zip_code = cep_data.get('cep', '')
                return location
        
        return None
    
    def _build_address_string(self, address: Dict) -> str:
        """Build a formatted address string from address components."""
        parts = []
        
        if address.get('road'):
            road = address['road']
            if address.get('house_number'):
                road = f"{road}, {address['house_number']}"
            parts.append(road)
        
        if address.get('suburb') or address.get('neighbourhood'):
            parts.append(address.get('suburb') or address.get('neighbourhood'))
        
        return ', '.join(parts) if parts else ''
    
    def _haversine_distance(
        self, 
        lat1: float, 
        lon1: float, 
        lat2: float, 
        lon2: float
    ) -> Decimal:
        """Calculate haversine distance between two points in km."""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371.0  # Earth's radius in km
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return Decimal(R * c).quantize(Decimal('0.01'))
    
    def _get_step_instruction(self, step: Dict, maneuver: Dict) -> str:
        """Generate human-readable instruction for a route step."""
        maneuver_type = maneuver.get('type', '')
        modifier = maneuver.get('modifier', '')
        name = step.get('name', '')
        
        instructions = {
            'depart': f"Siga em frente{' pela ' + name if name else ''}",
            'arrive': f"Você chegou ao destino{' em ' + name if name else ''}",
            'turn': self._get_turn_instruction(modifier, name),
            'continue': f"Continue{' pela ' + name if name else ''}",
            'merge': f"Entre na via{' ' + name if name else ''}",
            'on ramp': f"Pegue a rampa{' para ' + name if name else ''}",
            'off ramp': f"Saia pela rampa{' para ' + name if name else ''}",
            'fork': f"Mantenha-se à {self._translate_modifier(modifier)}{' para ' + name if name else ''}",
            'end of road': f"No final da via, vire à {self._translate_modifier(modifier)}",
            'roundabout': f"Na rotatória, pegue a saída{' para ' + name if name else ''}",
            'rotary': f"Na rotatória, pegue a saída{' para ' + name if name else ''}",
        }
        
        return instructions.get(maneuver_type, f"Continue{' pela ' + name if name else ''}")
    
    def _get_turn_instruction(self, modifier: str, name: str) -> str:
        """Generate turn instruction."""
        turn_types = {
            'left': 'Vire à esquerda',
            'right': 'Vire à direita',
            'slight left': 'Vire levemente à esquerda',
            'slight right': 'Vire levemente à direita',
            'sharp left': 'Vire acentuadamente à esquerda',
            'sharp right': 'Vire acentuadamente à direita',
            'uturn': 'Faça retorno',
            'straight': 'Continue em frente',
        }
        
        instruction = turn_types.get(modifier, 'Continue')
        if name:
            instruction += f" para {name}"
        
        return instruction
    
    def _translate_modifier(self, modifier: str) -> str:
        """Translate direction modifier to Portuguese."""
        translations = {
            'left': 'esquerda',
            'right': 'direita',
            'slight left': 'esquerda',
            'slight right': 'direita',
            'sharp left': 'esquerda',
            'sharp right': 'direita',
            'straight': 'frente',
        }
        return translations.get(modifier, modifier)


# Singleton instance
geocoding_service = GeocodingService()
