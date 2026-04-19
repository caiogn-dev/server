import logging
from typing import Optional, Dict, List, Tuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
GOOGLE_REVERSE_RESULT_TYPES = "street_address|premise|subpremise|route|intersection|neighborhood|sublocality|locality"


class GoogleMapsProvider:
    """Low-level Google Maps API client for server-side geo operations."""

    PALMAS_BOUNDS = "-10.45,-48.50|-10.05,-48.10"
    DEFAULT_CITY_SUFFIX = "Palmas, TO"

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
            if 'premise' in types:
                components.setdefault('street', long_name)
                components['premise'] = long_name
            if 'subpremise' in types:
                components['subpremise'] = long_name
            if 'street_number' in types:
                components['number'] = long_name
            if 'neighborhood' in types:
                components['neighborhood'] = long_name
            if 'sublocality' in types or 'sublocality_level_1' in types:
                components.setdefault('neighborhood', long_name)
            if 'administrative_area_level_3' in types:
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

    def _score_result(self, result: Dict) -> int:
        types = set(result.get('types', []))
        components = self._parse_address_components(result)

        type_weights = [
            ('street_address', 100),
            ('premise', 90),
            ('subpremise', 85),
            ('route', 75),
            ('intersection', 65),
            ('plus_code', 55),
            ('neighborhood', 45),
            ('sublocality', 40),
            ('locality', 35),
            ('administrative_area_level_2', 20),
        ]

        score = 0
        for result_type, weight in type_weights:
            if result_type in types:
                score += weight

        if components.get('street'):
            score += 20
        if components.get('number'):
            score += 20
        if components.get('neighborhood'):
            score += 10
        if components.get('city'):
            score += 10
        if result.get('formatted_address'):
            score += 5

        return score

    def _pick_best_result(self, results: List[Dict]) -> Optional[Dict]:
        if not results:
            return None
        return max(results, key=self._score_result)

    def _parse_geocode_result(self, result: Dict) -> Dict:
        location = result.get('geometry', {}).get('location', {})
        return {
            'lat': location.get('lat'),
            'lng': location.get('lng'),
            'formatted_address': result.get('formatted_address', ''),
            'place_id': result.get('place_id'),
            'address_components': self._parse_address_components(result),
            'result_types': result.get('types', []),
            'location_type': result.get('geometry', {}).get('location_type', ''),
        }

    def _is_precise_reverse_result(self, parsed_result: Dict) -> bool:
        result_types = set(parsed_result.get('result_types', []))
        location_type = parsed_result.get('location_type', '')
        components = parsed_result.get('address_components') or {}

        has_precise_type = bool(result_types & {'street_address', 'premise', 'subpremise'})
        has_precise_location = location_type in {'ROOFTOP', 'RANGE_INTERPOLATED'}
        has_street = bool(components.get('street'))
        has_number = bool(components.get('number'))

        return has_precise_type and has_precise_location and has_street and has_number

    def _sanitize_reverse_result(self, parsed_result: Dict) -> Dict:
        if self._is_precise_reverse_result(parsed_result):
            parsed_result['address_confidence'] = 'high'
            return parsed_result

        components = dict(parsed_result.get('address_components') or {})
        components.pop('street', None)
        components.pop('number', None)
        components.pop('premise', None)
        components.pop('subpremise', None)

        parsed_result['address_components'] = components
        parsed_result['formatted_address'] = ", ".join(
            part for part in [
                components.get('neighborhood'),
                components.get('city'),
                components.get('state_code') or components.get('state'),
                components.get('country'),
            ] if part
        ) or parsed_result.get('formatted_address', '')
        parsed_result['address_confidence'] = 'low'
        return parsed_result

    def _suggestion_from_geocode(self, geocoded: Dict | None) -> List[Dict]:
        if not geocoded:
            return []

        components = geocoded.get('address_components') or {}
        display_name = geocoded.get('formatted_address', '')
        secondary_text = ", ".join(part for part in [components.get('city'), components.get('state_code')] if part)

        return [{
            'display_name': display_name,
            'title': display_name,
            'subtitle': secondary_text,
            'main_text': components.get('street') or display_name,
            'secondary_text': secondary_text,
            'lat': geocoded.get('lat'),
            'lng': geocoded.get('lng'),
            'latitude': geocoded.get('lat'),
            'longitude': geocoded.get('lng'),
            'place_id': geocoded.get('place_id'),
        }]

    def _fallback_autosuggest(self, query: str) -> List[Dict]:
        normalized_query = query.strip()
        geocode_queries = [normalized_query]

        lower_query = normalized_query.lower()
        if 'palmas' not in lower_query and 'tocantins' not in lower_query and ' to' not in lower_query:
            geocode_queries.insert(0, f"{normalized_query}, {self.DEFAULT_CITY_SUFFIX}")

        for geocode_query in geocode_queries:
            geocoded = self.geocode(geocode_query, restrict_to_city=True)
            suggestions = self._suggestion_from_geocode(geocoded)
            if suggestions:
                return suggestions

        return []

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

        best_result = self._pick_best_result(payload['results'])
        if not best_result:
            return None
        return self._parse_geocode_result(best_result)

    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        if not self.api_key:
            return None

        base_params = {
            'latlng': f'{lat},{lng}',
            'key': self.api_key,
            'language': 'pt-BR',
            'region': 'br',
        }

        candidate_payloads: List[Dict] = []
        for extra_params in (
            {'result_type': GOOGLE_REVERSE_RESULT_TYPES},
            {},
        ):
            response = requests.get(
                GOOGLE_GEOCODE_URL,
                params={**base_params, **extra_params},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            candidate_payloads.append(payload)

            if payload.get('status') == 'OK' and payload.get('results'):
                best_result = self._pick_best_result(payload['results'])
                if best_result:
                    result = self._sanitize_reverse_result(self._parse_geocode_result(best_result))
                    result['lat'] = lat
                    result['lng'] = lng
                    return result

        statuses = [payload.get('status') for payload in candidate_payloads]
        logger.warning(
            "Google reverse geocode returned no usable results for lat=%s lng=%s statuses=%s",
            lat,
            lng,
            statuses,
        )
        return None

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

        status = payload.get('status')
        if status not in {'OK', 'ZERO_RESULTS'}:
            logger.warning("Google places autocomplete returned %s for query=%s", payload.get('status'), query[:80])
            return self._fallback_autosuggest(query)

        suggestions: List[Dict] = []
        for prediction in payload.get('predictions', [])[:limit]:
            formatting = prediction.get('structured_formatting', {})
            display_name = prediction.get('description', '')
            suggestions.append({
                'display_name': display_name,
                'title': prediction.get('description', ''),
                'subtitle': formatting.get('secondary_text', ''),
                'main_text': formatting.get('main_text', ''),
                'secondary_text': formatting.get('secondary_text', ''),
                'lat': None,
                'lng': None,
                'latitude': None,
                'longitude': None,
                'place_id': prediction.get('place_id'),
            })
        if suggestions:
            return suggestions
        return self._fallback_autosuggest(query)
