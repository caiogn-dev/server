import logging
from decimal import Decimal
from typing import Optional, Tuple

import requests
from django.conf import settings

from ..models import DeliveryZone, StoreLocation, ZipCodeGeo

logger = logging.getLogger(__name__)


class DeliveryDistanceService:
    def __init__(self):
        self.viacep_url = getattr(settings, 'VIACEP_URL', 'https://viacep.com.br/ws/{zip}/json/')
        self.geocode_url = getattr(settings, 'GEOCODE_URL', 'https://nominatim.openstreetmap.org/search')
        self.osrm_url = getattr(settings, 'OSRM_URL', 'https://router.project-osrm.org/route/v1/driving')
        self.user_agent = getattr(settings, 'GEOCODE_USER_AGENT', 'pastita-delivery/1.0')
        self.timeout_seconds = int(getattr(settings, 'DELIVERY_GEO_TIMEOUT', 10))

    @staticmethod
    def normalize_zip(zip_code: str) -> str:
        return ''.join(filter(str.isdigit, str(zip_code or '')))[:8]

    def _fetch_viacep(self, zip_code: str) -> Optional[dict]:
        try:
            response = requests.get(
                self.viacep_url.format(zip=zip_code),
                timeout=self.timeout_seconds
            )
            if response.status_code != 200:
                return None
            data = response.json()
            if data.get('erro'):
                return None
            return data
        except requests.RequestException as exc:
            logger.warning("ViaCEP lookup failed: %s", exc)
            return None

    def _build_geocode_query(self, zip_code: str, address_data: Optional[dict]) -> str:
        if not address_data:
            return f"{zip_code}, Brasil"

        parts = [
            address_data.get('logradouro', ''),
            address_data.get('bairro', ''),
            address_data.get('localidade', ''),
            address_data.get('uf', ''),
            zip_code,
            'Brasil',
        ]
        return ', '.join([part for part in parts if part])

    def _geocode(self, query: str) -> Optional[Tuple[Decimal, Decimal]]:
        try:
            response = requests.get(
                self.geocode_url,
                params={'format': 'json', 'limit': 1, 'q': query},
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout_seconds
            )
            if response.status_code != 200:
                return None
            results = response.json()
            if not results:
                return None
            return Decimal(results[0]['lat']), Decimal(results[0]['lon'])
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.warning("Geocode failed: %s", exc)
            return None

    def get_zip_location(self, zip_code: str) -> Optional[ZipCodeGeo]:
        clean_zip = self.normalize_zip(zip_code)
        if not clean_zip:
            return None

        cached = ZipCodeGeo.objects.filter(zip_code=clean_zip).first()
        if cached and cached.latitude and cached.longitude:
            return cached

        address_data = self._fetch_viacep(clean_zip)
        query = self._build_geocode_query(clean_zip, address_data)
        coords = self._geocode(query)
        if not coords:
            return None
        latitude, longitude = coords

        geo, _ = ZipCodeGeo.objects.update_or_create(
            zip_code=clean_zip,
            defaults={
                'address': (address_data or {}).get('logradouro', ''),
                'city': (address_data or {}).get('localidade', ''),
                'state': (address_data or {}).get('uf', ''),
                'latitude': latitude,
                'longitude': longitude,
            }
        )
        return geo

    def get_store_location(self) -> Optional[StoreLocation]:
        store = StoreLocation.objects.filter(is_active=True).order_by('-updated_at').first()
        if not store:
            return None
        if store.latitude and store.longitude:
            return store

        geo = self.get_zip_location(store.zip_code)
        if not geo:
            return store

        store.latitude = geo.latitude
        store.longitude = geo.longitude
        if not store.address:
            store.address = geo.address
        if not store.city:
            store.city = geo.city
        if not store.state:
            store.state = geo.state
        store.save(update_fields=['latitude', 'longitude', 'address', 'city', 'state', 'updated_at'])
        return store

    def _haversine_km(self, lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> Decimal:
        from math import radians, sin, cos, sqrt, atan2
        r = 6371.0
        d_lat = radians(float(lat2 - lat1))
        d_lon = radians(float(lon2 - lon1))
        a = sin(d_lat / 2) ** 2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(d_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return Decimal(r * c).quantize(Decimal('0.01'))

    def get_route_distance(self, origin: Tuple[Decimal, Decimal], dest: Tuple[Decimal, Decimal]) -> Tuple[Decimal, Optional[int]]:
        lat1, lon1 = origin
        lat2, lon2 = dest
        try:
            response = requests.get(
                f"{self.osrm_url}/{lon1},{lat1};{lon2},{lat2}",
                params={'overview': 'false'},
                timeout=self.timeout_seconds
            )
            if response.status_code == 200:
                data = response.json()
                routes = data.get('routes', [])
                if routes:
                    distance_km = Decimal(routes[0]['distance'] / 1000).quantize(Decimal('0.01'))
                    duration_min = int(routes[0]['duration'] / 60)
                    return distance_km, duration_min
        except requests.RequestException as exc:
            logger.warning("OSRM route failed: %s", exc)

        distance_km = self._haversine_km(lat1, lon1, lat2, lon2)
        return distance_km, None

    def calculate_delivery(self, zip_code: str) -> dict:
        store = self.get_store_location()
        if not store or not store.zip_code:
            return {
                'available': False,
                'error': 'STORE_LOCATION_NOT_SET',
            }

        destination = self.get_zip_location(zip_code)
        if not destination or destination.latitude is None or destination.longitude is None:
            return {
                'available': False,
                'error': 'ZIP_NOT_FOUND',
            }

        origin_coords = (store.latitude, store.longitude)
        dest_coords = (destination.latitude, destination.longitude)

        distance_km, duration_min = self.get_route_distance(origin_coords, dest_coords)
        rate = DeliveryZone.get_rate_for_distance(distance_km)
        if not rate:
            return {
                'available': False,
                'error': 'NO_RATE_FOR_DISTANCE',
                'distance_km': distance_km,
                'duration_min': duration_min,
            }

        return {
            'available': True,
            'fee': rate['fee'],
            'estimated_days': rate['estimated_days'],
            'zone_name': rate['zone_name'],
            'distance_km': distance_km,
            'duration_min': duration_min,
            'rate_per_km': rate['rate_per_km'],
            'min_fee': rate['min_fee'],
        }
