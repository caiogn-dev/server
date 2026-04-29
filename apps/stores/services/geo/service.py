import hashlib
import logging
import math
import re
import unicodedata
from decimal import Decimal
from typing import Optional, Dict, List, Tuple

from django.conf import settings
from django.core.cache import cache

from .google_provider import GoogleMapsProvider

logger = logging.getLogger(__name__)

CACHE_TTL_ROUTE = 86400
CACHE_TTL_GEOCODE = 86400
CACHE_TTL_ISOLINE = 21600


def _round_coords(lat: float, lng: float, precision: int = 4) -> Tuple[float, float]:
    return (round(lat, precision), round(lng, precision))


def _haversine_km(origin: Tuple[float, float], destination: Tuple[float, float]) -> float:
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
    key_data = f"{prefix}:{':'.join(str(a) for a in args)}"
    return hashlib.md5(key_data.encode()).hexdigest()[:32]


class GeoService:
    """Provider-agnostic geo service with Google as the primary backend."""

    DEFAULT_CITY_SUFFIX = "Palmas, Tocantins, Brasil"

    def __init__(self, provider: GoogleMapsProvider | None = None):
        self.provider = provider or GoogleMapsProvider()
        self.provider_name = getattr(settings, 'GEO_PROVIDER', 'google') or 'google'

    @staticmethod
    def _normalize_text(value: str) -> str:
        if not value:
            return ""
        normalized = unicodedata.normalize("NFD", str(value).lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    def _legacy_address_components(self, components: Dict[str, str]) -> Dict[str, str]:
        return {
            'street': components.get('street', ''),
            'houseNumber': components.get('number', ''),
            'house_number': components.get('number', ''),
            'district': components.get('neighborhood', ''),
            'neighborhood': components.get('neighborhood', ''),
            'city': components.get('city', ''),
            'state': components.get('state', ''),
            'stateCode': components.get('state_code', ''),
            'state_code': components.get('state_code', ''),
            'postalCode': components.get('zip_code', ''),
            'zip_code': components.get('zip_code', ''),
            'country': components.get('country', ''),
            'countryCode': components.get('country_code', ''),
            'country_code': components.get('country_code', ''),
        }

    def _normalize_geo_result(self, result: Dict) -> Dict:
        components = result.get('address_components') or {}
        legacy = self._legacy_address_components(components)
        lat = result.get('lat')
        lng = result.get('lng')
        formatted_address = result.get('formatted_address', '')
        normalized = {
            'lat': lat,
            'lng': lng,
            'latitude': lat,
            'longitude': lng,
            'formatted_address': formatted_address,
            'display_name': formatted_address,
            'place_id': result.get('place_id'),
            'address_confidence': result.get('address_confidence', 'high'),
            'address_components': components,
            'address': legacy,
            'provider': self.provider_name,
            'street': components.get('street', ''),
            'number': components.get('number', ''),
            'house_number': components.get('number', ''),
            'neighborhood': components.get('neighborhood', ''),
            'city': components.get('city', ''),
            'state': components.get('state', ''),
            'state_code': components.get('state_code', ''),
            'zip_code': components.get('zip_code', ''),
            'country': components.get('country', ''),
            'country_code': components.get('country_code', ''),
        }
        return normalized

    def _fallback_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> Dict:
        distance_km = round(_haversine_km(origin, destination), 2)
        avg_speed_kmh = 30.0
        duration_minutes = round((distance_km / avg_speed_kmh) * 60, 1) if avg_speed_kmh > 0 else 0
        duration_seconds = int(round(duration_minutes * 60))
        return {
            'distance_km': distance_km,
            'distance_meters': int(round(distance_km * 1000)),
            'duration_minutes': duration_minutes,
            'duration_seconds': duration_seconds,
            'polyline': '',
            'departure': {},
            'arrival': {},
            'fallback': True,
            'provider': self.provider_name,
        }

    def _normalize_route_result(self, result: Dict, origin: Tuple[float, float], destination: Tuple[float, float]) -> Dict:
        if not result:
            return self._fallback_route(origin, destination)

        distance_meters = int(result.get('distance_meters', 0))
        duration_seconds = int(result.get('duration_seconds', 0))
        return {
            'distance_km': round(distance_meters / 1000, 2),
            'distance_meters': distance_meters,
            'duration_minutes': round(duration_seconds / 60, 1),
            'duration_seconds': duration_seconds,
            'polyline': result.get('polyline') or '',
            'departure': result.get('departure', {}),
            'arrival': result.get('arrival', {}),
            'fallback': False,
            'provider': self.provider_name,
        }

    def _match_fixed_price_zone(
        self,
        store,
        customer_lat: float,
        customer_lng: float,
        address_text: str = "",
    ) -> Optional[Dict]:
        """Retorna a zona fixa correspondente ao endereço do cliente, ou None.

        Campos suportados em cada zona (store.metadata['fixed_price_zones']):
          name        (str)   — nome da zona
          fee         (float) — taxa fixa; ignorado se surcharge_on_km=True
          keywords    (list)  — termos buscados no endereço reverso
          surcharge_on_km (bool)  — se True, soma 'surcharge' à taxa por km em vez de substituir
          surcharge   (float) — valor extra adicionado à taxa por km (ex.: R$5 para condos fechados)
        """
        metadata = getattr(store, 'metadata', None) or {}
        fixed_price_zones = metadata.get('fixed_price_zones') or []
        if not fixed_price_zones:
            return None

        reverse = self.reverse_geocode(customer_lat, customer_lng) or {}
        searchable_parts = [
            address_text,
            reverse.get('formatted_address', ''),
            reverse.get('street', ''),
            reverse.get('neighborhood', ''),
            reverse.get('sublocality', ''),
            reverse.get('city', ''),
            reverse.get('state', ''),
        ]
        searchable_text = self._normalize_text(" | ".join(part for part in searchable_parts if part))
        if not searchable_text:
            return None

        for zone in fixed_price_zones:
            keywords = list(zone.get('keywords') or [])
            if zone.get('name'):
                keywords.append(zone['name'])

            normalized_keywords = [self._normalize_text(kw) for kw in keywords if kw]
            if any(kw and kw in searchable_text for kw in normalized_keywords):
                return zone

        return None

    def _matches_dynamic_delivery_area(
        self,
        store,
        customer_lat: float | None = None,
        customer_lng: float | None = None,
        address_text: str = "",
    ) -> bool:
        """Return True when a store-specific dynamic delivery area allows km pricing.

        If ``metadata.dynamic_delivery_area_keywords`` is absent, legacy stores keep
        the old behavior and dynamic pricing remains unrestricted.
        """
        metadata = getattr(store, 'metadata', None) or {}
        keywords = metadata.get('dynamic_delivery_area_keywords') or []
        if not keywords:
            return True

        def _matches(text: str) -> bool:
            normalized_text = self._normalize_text(text)
            if not normalized_text:
                return False

            # Palmas' Plano Diretor addresses are often written as "404 Sul" or
            # "103 Norte", while reverse geocoding may return ARSE/ARNO aliases.
            if re.search(r'\b\d{3}\s*(sul|norte)\b', normalized_text):
                return True

            normalized_keywords = [self._normalize_text(kw) for kw in keywords if kw]
            return any(kw and kw in normalized_text for kw in normalized_keywords)

        if address_text:
            return _matches(address_text)

        searchable_parts = []
        if customer_lat is not None and customer_lng is not None:
            reverse = self.reverse_geocode(customer_lat, customer_lng) or {}
            searchable_parts.extend([
                reverse.get('formatted_address', ''),
                reverse.get('street', ''),
                reverse.get('neighborhood', ''),
                reverse.get('sublocality', ''),
                reverse.get('city', ''),
            ])

        searchable_text = self._normalize_text(" | ".join(part for part in searchable_parts if part))
        if not searchable_text:
            return False

        return _matches(searchable_text)

    def _build_circle_polygon(self, center: Tuple[float, float], radius_km: float, points: int = 24) -> List[Dict[str, float]]:
        lat, lng = center
        lat_rad = math.radians(lat)
        km_per_deg_lat = 111.32
        km_per_deg_lng = max(111.32 * math.cos(lat_rad), 0.01)
        polygon: List[Dict[str, float]] = []

        for step in range(points + 1):
            angle = (2 * math.pi * step) / points
            dlat = (radius_km * math.sin(angle)) / km_per_deg_lat
            dlng = (radius_km * math.cos(angle)) / km_per_deg_lng
            polygon.append({'lat': lat + dlat, 'lng': lng + dlng})
        return polygon

    def geocode(self, address: str, country: str = "BRA", restrict_to_city: bool = True) -> Optional[Dict]:
        query = address.strip()
        if restrict_to_city:
            lower_q = query.lower()
            if 'palmas' not in lower_q and 'tocantins' not in lower_q:
                query = f"{query}, {self.DEFAULT_CITY_SUFFIX}"

        cache_key = _make_cache_key("geocode", query.strip().lower(), country, restrict_to_city)
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            result = self.provider.geocode(query, country=country, restrict_to_city=restrict_to_city)
            if not result and restrict_to_city:
                return self.geocode(address, country=country, restrict_to_city=False)
            if not result:
                return None

            normalized = self._normalize_geo_result(result)
            cache.set(cache_key, normalized, CACHE_TTL_GEOCODE)
            return normalized
        except Exception as exc:
            logger.error("Geocode error: %s", exc, exc_info=True)
            return None

    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        rounded_lat, rounded_lng = _round_coords(lat, lng, 4)
        cache_key = _make_cache_key("revgeo", rounded_lat, rounded_lng)
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            result = self.provider.reverse_geocode(lat, lng)
            if not result:
                return None
            normalized = self._normalize_geo_result(result)
            cache.set(cache_key, normalized, CACHE_TTL_GEOCODE)
            return normalized
        except Exception as exc:
            logger.error("Reverse geocode error: %s", exc, exc_info=True)
            return None

    def _resolve_destination(
        self,
        destination: Tuple[float, float] | str,
    ) -> Tuple[float, float] | None:
        if isinstance(destination, tuple):
            return destination

        geocoded = self.geocode(destination)
        if not geocoded:
            return None

        lat = geocoded.get('lat')
        lng = geocoded.get('lng')
        if lat is None or lng is None:
            return None

        return (float(lat), float(lng))

    def _get_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float] | str,
        transport_mode: str = "car",
    ) -> Dict:
        resolved_destination = self._resolve_destination(destination)
        if not resolved_destination:
            return self._fallback_route(origin, origin)

        origin_rounded = _round_coords(origin[0], origin[1], 4)
        dest_rounded = _round_coords(resolved_destination[0], resolved_destination[1], 4)
        cache_key = _make_cache_key("route", origin_rounded, dest_rounded, transport_mode)
        cached = cache.get(cache_key)
        if cached:
            return cached

        google_mode = {
            'car': 'driving',
            'pedestrian': 'walking',
            'bicycle': 'bicycling',
            'truck': 'driving',
        }.get(transport_mode, 'driving')

        try:
            result = self.provider.route(origin, resolved_destination, transport_mode=google_mode)
            normalized = self._normalize_route_result(result, origin, resolved_destination)
            cache.set(cache_key, normalized, CACHE_TTL_ROUTE)
            return normalized
        except Exception as exc:
            logger.error("Route calculation error: %s", exc, exc_info=True)
            return self._fallback_route(origin, resolved_destination)

    def calculate_route(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        transport_mode: str = "car",
    ) -> Optional[Dict]:
        return self._get_route(origin, destination, transport_mode=transport_mode)

    def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
    ) -> Optional[Decimal]:
        route = self.calculate_route(origin, destination)
        if route:
            return Decimal(str(route['distance_km']))
        return None

    def get_isoline(
        self,
        center: Tuple[float, float],
        range_type: str = "time",
        range_value: int = 900,
        transport_mode: str = "car",
    ) -> Optional[Dict]:
        center_rounded = _round_coords(center[0], center[1], 3)
        cache_key = _make_cache_key("isoline", center_rounded, range_type, range_value, transport_mode)
        cached = cache.get(cache_key)
        if cached:
            return cached

        if range_type == "time":
            radius_km = max((range_value / 3600) * 30.0, 0.5)
        else:
            radius_km = max(range_value / 1000, 0.5)

        result = {
            'range_type': range_type,
            'range_value': range_value,
            'transport_mode': transport_mode,
            'polygons': [self._build_circle_polygon(center, radius_km)],
            'center': {'lat': center[0], 'lng': center[1]},
            'provider': self.provider_name,
            'approximate': True,
        }
        cache.set(cache_key, result, CACHE_TTL_ISOLINE)
        return result

    def get_delivery_zones_isolines(
        self,
        center: Tuple[float, float],
        time_ranges: List[int] | None = None,
    ) -> List[Dict]:
        if time_ranges is None:
            time_ranges = [10, 20, 30, 45]

        zones = []
        for minutes in time_ranges:
            isoline = self.get_isoline(
                center=center,
                range_type="time",
                range_value=minutes * 60,
                transport_mode="car",
            )
            if isoline:
                isoline['minutes'] = minutes
                zones.append(isoline)
        return zones

    def autosuggest(
        self,
        query: str,
        center: Tuple[float, float] | None = None,
        country: str = "BRA",
        limit: int = 5,
    ) -> List[Dict]:
        try:
            return self.provider.autosuggest(query, center=center, limit=limit)
        except Exception as exc:
            logger.error("Autosuggest error: %s", exc, exc_info=True)
            return []

    def validate_delivery_address(
        self,
        store_location: Tuple[float, float],
        delivery_address: Tuple[float, float],
        max_distance_km: float = 20.0,
        max_time_minutes: float = 45.0,
    ) -> Dict:
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
                'polyline': polyline,
                'message': f'Endereço fora da área de entrega (máx: {max_distance_km}km)',
            }

        if duration_minutes > max_time_minutes:
            return {
                'is_valid': False,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'polyline': polyline,
                'message': f'Tempo de entrega muito longo (máx: {max_time_minutes}min)',
            }

        return {
            'is_valid': True,
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'polyline': polyline,
            'message': 'Endereço válido para entrega',
        }

    def _get_checkout_service_cls(self):
        from apps.stores.services.checkout_service import CheckoutService

        return CheckoutService

    def calculate_delivery_fee(
        self,
        store,
        customer_lat: float | None = None,
        customer_lng: float | None = None,
        destination_address: str | None = None,
        rain_surcharge: bool = False,
        customer_address_text: str | None = None,
    ) -> Dict:
        """Calcula a taxa de entrega aplicando, em ordem de prioridade:

        1. Zona fixa por bairro/região (ex.: Taquaralto R$40, Aeroporto R$45)
        2. Zona de condomínio plana (ex.: Caribe/Polinésia R$25)
        3. Zona de condomínio fechado com sobretaxa (ex.: Alphaville = km_fee + R$5)
        4. StoreDeliveryZone configuradas no banco
        5. Cálculo dinâmico: R$9 plano até 4 km, +R$1,10/km após isso
        6. Acima de 16 km → fee=None (a combinar)

        Parâmetro extra:
          rain_surcharge (bool) — adiciona R$2,00 quando está chovendo
        """
        from apps.stores.models import StoreDeliveryZone

        RAIN_EXTRA = Decimal('2.00')

        metadata = getattr(store, 'metadata', None) or {}
        address_data = getattr(store, 'address_data', None) or {}

        store_lat = (
            getattr(store, 'latitude', None)
            or address_data.get('lat')
            or metadata.get('store_latitude')
        )
        store_lng = (
            getattr(store, 'longitude', None)
            or address_data.get('lng')
            or metadata.get('store_longitude')
        )

        if not store_lat or not store_lng:
            base = float(store.default_delivery_fee or Decimal('0.00'))
            return {
                'fee': base + float(RAIN_EXTRA) if rain_surcharge else base,
                'distance_km': None,
                'duration_minutes': None,
                'is_within_area': True,
                'zone': None,
                'message': 'Taxa de entrega padrão aplicada',
            }

        address_text = customer_address_text or destination_address or ""
        customer_location_known = customer_lat is not None and customer_lng is not None
        if customer_location_known:
            route = self._get_route(
                (float(store_lat), float(store_lng)),
                (float(customer_lat), float(customer_lng)),
            )
        elif destination_address:
            route = self._get_route(
                (float(store_lat), float(store_lng)),
                destination_address,
            )
        else:
            route = None

        if not route:
            return {
                'fee': float(store.default_delivery_fee or Decimal('0.00')),
                'distance_km': None,
                'duration_minutes': None,
                'is_within_area': False,
                'zone': None,
                'message': 'Não foi possível geocodificar o endereço',
            }

        distance_km = route['distance_km']
        duration_minutes = route['duration_minutes']
        polyline = route.get('polyline')

        def _apply_rain(fee_val):
            if fee_val is None:
                return None
            return float(Decimal(str(fee_val)) + RAIN_EXTRA) if rain_surcharge else float(fee_val)

        # ── 1-3. Zonas fixas / condomínios (metadado fixed_price_zones) ──────
        fixed_zone = None
        if customer_location_known:
            fixed_zone = self._match_fixed_price_zone(
                store, float(customer_lat), float(customer_lng), address_text=address_text
            )

        if fixed_zone:
            zone_name = fixed_zone.get('name') or 'Zona especial'
            is_additive = fixed_zone.get('surcharge_on_km', False)

            if is_additive:
                # Condomínio fechado: taxa por km + sobretaxa fixa
                surcharge_val = Decimal(str(fixed_zone.get('surcharge', '5.00')))
                checkout_service_cls = self._get_checkout_service_cls()
                km_fee_info = checkout_service_cls._calculate_dynamic_fee(
                    store, Decimal(str(distance_km))
                )
                km_fee = km_fee_info.get('fee')
                if km_fee is None:
                    fee_val = None
                else:
                    fee_val = float(Decimal(str(km_fee)) + surcharge_val)
                message = (
                    f"Condomínio fechado: taxa por km + R$ {surcharge_val:.2f} de acesso"
                )
            else:
                fee_val = float(Decimal(str(fixed_zone.get('fee', store.default_delivery_fee or 0))))
                message = f"Entrega com taxa fixa para a região: {zone_name}"

            return {
                'fee': _apply_rain(fee_val),
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'is_within_area': fee_val is not None,
                'zone': {'id': None, 'name': zone_name, 'min_distance': None, 'max_distance': None},
                'polyline': polyline,
                'rain_surcharge_applied': rain_surcharge,
                'message': message,
            }

        if not self._matches_dynamic_delivery_area(
            store,
            float(customer_lat) if customer_location_known else None,
            float(customer_lng) if customer_location_known else None,
            address_text=address_text,
        ):
            area_label = metadata.get(
                'dynamic_delivery_area_label',
                'Plano Diretor Norte/Sul',
            )
            return {
                'fee': None,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'is_within_area': False,
                'zone': None,
                'polyline': polyline,
                'rain_surcharge_applied': False,
                'reason': 'outside_dynamic_delivery_area',
                'message': f'Entrega dinâmica disponível apenas para {area_label}.',
            }

        # ── 4. StoreDeliveryZone configuradas no banco ────────────────────────
        delivery_zones = StoreDeliveryZone.objects.filter(
            store=store, is_active=True,
        ).order_by('min_km')

        if delivery_zones.exists():
            for zone in delivery_zones:
                if zone.matches_distance(distance_km):
                    fee = zone.calculate_fee(distance_km)
                    return {
                        'fee': _apply_rain(float(fee)),
                        'distance_km': distance_km,
                        'duration_minutes': duration_minutes,
                        'is_within_area': True,
                        'zone': {
                            'id': str(zone.id),
                            'name': zone.name,
                            'min_distance': zone.min_km,
                            'max_distance': zone.max_km,
                        },
                        'polyline': polyline,
                        'rain_surcharge_applied': rain_surcharge,
                        'message': f'Entrega na zona: {zone.name}',
                    }

        # ── 5-6. Cálculo dinâmico (base R$9, +R$1,00/km após 4 km, >16 km=None) ──
        checkout_service_cls = self._get_checkout_service_cls()
        fee_info = checkout_service_cls._calculate_dynamic_fee(store, Decimal(str(distance_km)))
        raw_fee = fee_info.get('fee')

        if raw_fee is None:
            return {
                'fee': None,
                'distance_km': distance_km,
                'duration_minutes': duration_minutes,
                'is_within_area': False,
                'zone': None,
                'polyline': polyline,
                'rain_surcharge_applied': False,
                'message': fee_info.get('message', 'Distância acima do limite — entrar em contato'),
            }

        final_fee = _apply_rain(raw_fee)
        return {
            'fee': final_fee,
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'is_within_area': True,
            'zone': None,
            'polyline': polyline,
            'rain_surcharge_applied': rain_surcharge,
            'message': (
                f"Taxa: R$ {final_fee:.2f} ({distance_km:.1f} km)"
                + (" + R$2,00 chuva" if rain_surcharge else "")
            ),
        }


geo_service = GeoService()
