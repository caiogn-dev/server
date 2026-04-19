import logging
from typing import Optional, Dict, List, Tuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"


class GoogleMapsProvider:
    """Low-level Google Maps API client for server-side geo operations."""

    PALMAS_BOUNDS = "-10.45,-48.50|-10.05,-48.10"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, 'GOOGLE_MAPS_KEY', '').strip()

    def _parse_address_components(self, result: Dict) -> Dict[str, str]:
        components: Dict[str, str] = {}
        for component in result.get('address_components', []):
            types = set(component.get('types', []))
            long_name = component.get('long_name', '')
            short_name = component.get('short_name', '')

            if 'route' in types:
                components['street'] = long_name
            if 'street_number' in types:
                components['number'] = long_name
            if 'neighborhood' in types:
                components['neighborhood'] = long_name
            if 'sublocality' in types or 'sublocality_level_1' in types:
                components.setdefault('neighborhood', long_name)
            if 'locality' in types:
                components['city'] = long_name
            if 'administrative_area_level_2' in types:
                components.setdefault('city', long_name)
            if 'administrative_area_level_1' in types:
                components['state'] = long_name
                components['state_code'] = short_name
            if 'postal_code' in types:
                components['zip_code'] = long_name
            if 'country' in types:
                components['country'] = long_name
                components['country_code'] = short_name

        return components

    def _parse_geocode_result(self, result: Dict) -> Dict:
        location = result.get('geometry', {}).get('location', {})
        return {
            'lat': location.get('lat'),
            'lng': location.get('lng'),
            'formatted_address': result.get('formatted_address', ''),
            'place_id': result.get('place_id'),
            'address_components': self._parse_address_components(result),
        }

    def geocode(
        self,
        query: str,
        *,
        country: str = "BRA",
        restrict_to_city: bool = True,
    ) -> Optional[Dict]:
        if not self.api_key:
            return None

        params = {
            'address': query,
            'key': self.api_key,
            'language': 'pt-BR',
            'region': 'br',
        }

        if restrict_to_city:
            params['bounds'] = self.PALMAS_BOUNDS
            params['components'] = 'country:BR|administrative_area:TO|locality:Palmas'
        elif country:
            params['components'] = f'country:{country[:2]}'

        response = requests.get(GOOGLE_GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()

        if payload.get('status') != 'OK' or not payload.get('results'):
            logger.warning("Google geocode returned %s for query=%s", payload.get('status'), query[:80])
            return None

        return self._parse_geocode_result(payload['results'][0])

    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        if not self.api_key:
            return None

        response = requests.get(
            GOOGLE_GEOCODE_URL,
            params={
                'latlng': f'{lat},{lng}',
                'key': self.api_key,
                'language': 'pt-BR',
                'region': 'br',
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get('status') != 'OK' or not payload.get('results'):
            logger.warning("Google reverse geocode returned %s for lat=%s lng=%s", payload.get('status'), lat, lng)
            return None

        result = self._parse_geocode_result(payload['results'][0])
        result['lat'] = lat
        result['lng'] = lng
        return result

    def route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        *,
        transport_mode: str = "driving",
    ) -> Optional[Dict]:
        if not self.api_key:
            return None

        response = requests.get(
            GOOGLE_DIRECTIONS_URL,
            params={
                'origin': f'{origin[0]},{origin[1]}',
                'destination': f'{destination[0]},{destination[1]}',
                'mode': transport_mode,
                'language': 'pt-BR',
                'region': 'br',
                'key': self.api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get('status') != 'OK' or not payload.get('routes'):
            logger.warning(
                "Google directions returned %s for origin=%s destination=%s",
                payload.get('status'),
                origin,
                destination,
            )
            return None

        route = payload['routes'][0]
        legs = route.get('legs', [])
        distance_meters = sum(int(leg.get('distance', {}).get('value', 0)) for leg in legs)
        duration_seconds = sum(int(leg.get('duration', {}).get('value', 0)) for leg in legs)
        polyline = route.get('overview_polyline', {}).get('points')

        return {
            'distance_meters': distance_meters,
            'duration_seconds': duration_seconds,
            'polyline': polyline,
            'departure': legs[0].get('start_location', {}) if legs else {},
            'arrival': legs[-1].get('end_location', {}) if legs else {},
        }

    def autosuggest(
        self,
        query: str,
        *,
        center: Tuple[float, float] | None = None,
        limit: int = 5,
    ) -> List[Dict]:
        if not self.api_key:
            return []

        params = {
            'input': query,
            'key': self.api_key,
            'language': 'pt-BR',
            'components': 'country:br',
        }
        if center:
            params['location'] = f'{center[0]},{center[1]}'
            params['radius'] = 30000

        response = requests.get(GOOGLE_PLACES_AUTOCOMPLETE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()

        if payload.get('status') not in {'OK', 'ZERO_RESULTS'}:
            logger.warning("Google places autocomplete returned %s for query=%s", payload.get('status'), query[:80])
            return []

        suggestions: List[Dict] = []
        for prediction in payload.get('predictions', [])[:limit]:
            formatting = prediction.get('structured_formatting', {})
            suggestions.append({
                'title': prediction.get('description', ''),
                'subtitle': formatting.get('secondary_text', ''),
                'lat': None,
                'lng': None,
                'place_id': prediction.get('place_id'),
            })
        return suggestions
