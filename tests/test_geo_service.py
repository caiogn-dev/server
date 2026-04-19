"""
TDD tests for GeoService (Google Maps) and GoogleMapsProvider.

Coverage:
- GoogleMapsProvider: address component parsing, geocode, reverse_geocode, route, autosuggest
- GeoService: caching, restrict_to_city, haversine fallback, delivery fee tiers, validation
"""
import math
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.stores.services.geo.google_provider import GoogleMapsProvider
from apps.stores.services.geo.service import GeoService, _haversine_km


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _google_geocode_ok(lat=-10.184, lng=-48.334, formatted="Rua das Flores, 10, Plano Diretor Sul, Palmas - TO, 77016-002, Brasil"):
    return {
        'status': 'OK',
        'results': [{
            'geometry': {'location': {'lat': lat, 'lng': lng}},
            'formatted_address': formatted,
            'place_id': 'ChIJfake123',
            'address_components': [
                {'long_name': 'Rua das Flores', 'short_name': 'R. das Flores', 'types': ['route']},
                {'long_name': '10', 'short_name': '10', 'types': ['street_number']},
                {'long_name': 'Plano Diretor Sul', 'short_name': 'PDS', 'types': ['neighborhood', 'political']},
                {'long_name': 'Palmas', 'short_name': 'Palmas', 'types': ['locality', 'political']},
                {'long_name': 'Tocantins', 'short_name': 'TO', 'types': ['administrative_area_level_1', 'political']},
                {'long_name': '77016-002', 'short_name': '77016-002', 'types': ['postal_code']},
                {'long_name': 'Brasil', 'short_name': 'BR', 'types': ['country', 'political']},
            ],
        }],
    }


def _google_geocode_zero():
    return {'status': 'ZERO_RESULTS', 'results': []}


def _google_directions_ok(distance_m=5000, duration_s=600, polyline='abc123'):
    return {
        'status': 'OK',
        'routes': [{
            'overview_polyline': {'points': polyline},
            'legs': [{
                'distance': {'value': distance_m},
                'duration': {'value': duration_s},
                'start_location': {'lat': -10.184, 'lng': -48.334},
                'end_location': {'lat': -10.200, 'lng': -48.350},
            }],
        }],
    }


def _google_places_ok(predictions=None):
    predictions = predictions or [
        {
            'description': 'Quadra 304 Norte, Palmas, TO, Brasil',
            'place_id': 'place_001',
            'structured_formatting': {'secondary_text': 'Palmas, Tocantins'},
        }
    ]
    return {'status': 'OK', 'predictions': predictions}


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# GoogleMapsProvider — address component parsing
# ---------------------------------------------------------------------------

class ParseAddressComponentsTest(TestCase):
    def setUp(self):
        self.provider = GoogleMapsProvider(api_key='test-key')

    def test_all_standard_components_mapped(self):
        result = _google_geocode_ok()['results'][0]
        comps = self.provider._parse_address_components(result)
        self.assertEqual(comps['street'], 'Rua das Flores')
        self.assertEqual(comps['number'], '10')
        self.assertEqual(comps['neighborhood'], 'Plano Diretor Sul')
        self.assertEqual(comps['city'], 'Palmas')
        self.assertEqual(comps['state'], 'Tocantins')
        self.assertEqual(comps['state_code'], 'TO')
        self.assertEqual(comps['zip_code'], '77016-002')
        self.assertEqual(comps['country'], 'Brasil')
        self.assertEqual(comps['country_code'], 'BR')

    def test_sublocality_used_as_neighborhood_fallback(self):
        result = {
            'address_components': [
                {'long_name': 'Centro', 'short_name': 'Centro', 'types': ['sublocality', 'sublocality_level_1']},
                {'long_name': 'Palmas', 'short_name': 'Palmas', 'types': ['locality']},
            ]
        }
        comps = self.provider._parse_address_components(result)
        self.assertEqual(comps['neighborhood'], 'Centro')

    def test_neighborhood_type_takes_priority_over_sublocality(self):
        result = {
            'address_components': [
                {'long_name': 'Bairro Oficial', 'short_name': '', 'types': ['neighborhood']},
                {'long_name': 'Sublocal', 'short_name': '', 'types': ['sublocality']},
            ]
        }
        comps = self.provider._parse_address_components(result)
        self.assertEqual(comps['neighborhood'], 'Bairro Oficial')

    def test_admin_level2_used_as_city_fallback(self):
        result = {
            'address_components': [
                {'long_name': 'Palmas', 'short_name': 'Palmas', 'types': ['administrative_area_level_2']},
            ]
        }
        comps = self.provider._parse_address_components(result)
        self.assertEqual(comps['city'], 'Palmas')

    def test_empty_result_returns_empty_dict(self):
        comps = self.provider._parse_address_components({'address_components': []})
        self.assertEqual(comps, {})


# ---------------------------------------------------------------------------
# GoogleMapsProvider — geocode
# ---------------------------------------------------------------------------

class GoogleProviderGeocodeTest(TestCase):
    def setUp(self):
        self.provider = GoogleMapsProvider(api_key='test-key')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_geocode_ok_returns_structured_result(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_ok())
        result = self.provider.geocode('Rua das Flores, 10, Palmas')
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['lat'], -10.184)
        self.assertAlmostEqual(result['lng'], -48.334)
        self.assertEqual(result['place_id'], 'ChIJfake123')
        self.assertEqual(result['address_components']['street'], 'Rua das Flores')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_geocode_zero_results_returns_none(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_zero())
        result = self.provider.geocode('Endereço Inexistente XYZ 999')
        self.assertIsNone(result)

    def test_geocode_no_api_key_returns_none(self):
        provider = GoogleMapsProvider(api_key='')
        result = provider.geocode('Qualquer coisa')
        self.assertIsNone(result)

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_geocode_restrict_to_city_adds_bounds_and_components(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_ok())
        self.provider.geocode('Quadra 304 Norte', restrict_to_city=True)
        call_params = mock_get.call_args[1]['params']
        self.assertIn('bounds', call_params)
        self.assertIn('Palmas', call_params.get('components', ''))

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_geocode_without_restrict_uses_country_component(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_ok())
        self.provider.geocode('Rua das Flores', restrict_to_city=False)
        call_params = mock_get.call_args[1]['params']
        self.assertNotIn('bounds', call_params)
        self.assertIn('BR', call_params.get('components', ''))


# ---------------------------------------------------------------------------
# GoogleMapsProvider — reverse_geocode
# ---------------------------------------------------------------------------

class GoogleProviderReverseGeocodeTest(TestCase):
    def setUp(self):
        self.provider = GoogleMapsProvider(api_key='test-key')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_reverse_geocode_preserves_input_coords(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_ok(lat=-10.200, lng=-48.340))
        result = self.provider.reverse_geocode(-10.200, -48.340)
        # lat/lng on the result must match what we passed, not what the API returned
        self.assertAlmostEqual(result['lat'], -10.200)
        self.assertAlmostEqual(result['lng'], -48.340)

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_reverse_geocode_includes_address_components(self, mock_get):
        mock_get.return_value = _mock_response(_google_geocode_ok())
        result = self.provider.reverse_geocode(-10.184, -48.334)
        self.assertIn('address_components', result)
        self.assertEqual(result['address_components']['city'], 'Palmas')

    def test_reverse_geocode_no_api_key_returns_none(self):
        provider = GoogleMapsProvider(api_key='')
        self.assertIsNone(provider.reverse_geocode(-10.184, -48.334))


# ---------------------------------------------------------------------------
# GoogleMapsProvider — route
# ---------------------------------------------------------------------------

class GoogleProviderRouteTest(TestCase):
    def setUp(self):
        self.provider = GoogleMapsProvider(api_key='test-key')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_route_ok_parses_distance_duration_polyline(self, mock_get):
        mock_get.return_value = _mock_response(_google_directions_ok(distance_m=8000, duration_s=900, polyline='xyz'))
        result = self.provider.route((-10.184, -48.334), (-10.200, -48.350))
        self.assertEqual(result['distance_meters'], 8000)
        self.assertEqual(result['duration_seconds'], 900)
        self.assertEqual(result['polyline'], 'xyz')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_route_sums_multiple_legs(self, mock_get):
        payload = {
            'status': 'OK',
            'routes': [{
                'overview_polyline': {'points': 'multi'},
                'legs': [
                    {'distance': {'value': 3000}, 'duration': {'value': 400}, 'start_location': {}, 'end_location': {}},
                    {'distance': {'value': 2000}, 'duration': {'value': 200}, 'start_location': {}, 'end_location': {}},
                ],
            }],
        }
        mock_get.return_value = _mock_response(payload)
        result = self.provider.route((-10.184, -48.334), (-10.200, -48.350))
        self.assertEqual(result['distance_meters'], 5000)
        self.assertEqual(result['duration_seconds'], 600)

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_route_no_routes_returns_none(self, mock_get):
        mock_get.return_value = _mock_response({'status': 'NOT_FOUND', 'routes': []})
        result = self.provider.route((-10.184, -48.334), (-10.200, -48.350))
        self.assertIsNone(result)

    def test_route_no_api_key_returns_none(self):
        provider = GoogleMapsProvider(api_key='')
        result = provider.route((-10.184, -48.334), (-10.200, -48.350))
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# GoogleMapsProvider — autosuggest
# ---------------------------------------------------------------------------

class GoogleProviderAutosuggestTest(TestCase):
    def setUp(self):
        self.provider = GoogleMapsProvider(api_key='test-key')

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_autosuggest_returns_parsed_predictions(self, mock_get):
        mock_get.return_value = _mock_response(_google_places_ok())
        results = self.provider.autosuggest('Quadra 304')
        self.assertEqual(len(results), 1)
        self.assertIn('title', results[0])
        self.assertEqual(results[0]['place_id'], 'place_001')
        self.assertIsNone(results[0]['lat'])  # autocomplete does not return coords

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_autosuggest_zero_results_returns_empty_list(self, mock_get):
        mock_get.return_value = _mock_response({'status': 'ZERO_RESULTS', 'predictions': []})
        results = self.provider.autosuggest('xyzxyzxyz')
        self.assertEqual(results, [])

    def test_autosuggest_no_api_key_returns_empty(self):
        provider = GoogleMapsProvider(api_key='')
        self.assertEqual(provider.autosuggest('anything'), [])

    @patch('apps.stores.services.geo.google_provider.requests.get')
    def test_autosuggest_respects_limit(self, mock_get):
        mock_get.return_value = _mock_response(_google_places_ok(predictions=[
            {'description': f'Rua {i}', 'place_id': f'p{i}', 'structured_formatting': {}}
            for i in range(10)
        ]))
        results = self.provider.autosuggest('Rua', limit=3)
        self.assertLessEqual(len(results), 3)


# ---------------------------------------------------------------------------
# Haversine helper
# ---------------------------------------------------------------------------

class HaversineTest(TestCase):
    def test_same_point_is_zero(self):
        self.assertAlmostEqual(_haversine_km((-10.184, -48.334), (-10.184, -48.334)), 0.0, places=3)

    def test_known_distance_approx(self):
        # ~5 km offset along latitude
        origin = (-10.184, -48.334)
        dest = (-10.229, -48.334)
        dist = _haversine_km(origin, dest)
        self.assertGreater(dist, 4.0)
        self.assertLess(dist, 6.0)


# ---------------------------------------------------------------------------
# GeoService — geocode (with caching)
# ---------------------------------------------------------------------------

class GeoServiceGeocodeTest(TestCase):
    def setUp(self):
        self.provider = MagicMock(spec=GoogleMapsProvider)
        self.service = GeoService(provider=self.provider)

    def _make_provider_result(self, lat=-10.184, lng=-48.334):
        return {
            'lat': lat,
            'lng': lng,
            'formatted_address': 'Rua das Flores, 10, Palmas',
            'place_id': 'ChIJfake',
            'address_components': {
                'street': 'Rua das Flores',
                'number': '10',
                'neighborhood': 'Plano Diretor Sul',
                'city': 'Palmas',
                'state': 'Tocantins',
                'state_code': 'TO',
                'zip_code': '77016-002',
                'country': 'Brasil',
                'country_code': 'BR',
            },
        }

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_returns_normalized_result(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.geocode.return_value = self._make_provider_result()
        result = self.service.geocode('Rua das Flores, 10')
        self.assertIsNotNone(result)
        self.assertEqual(result['lat'], -10.184)
        self.assertEqual(result['street'], 'Rua das Flores')
        self.assertEqual(result['provider'], 'google')

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_restrict_to_city_appends_city_suffix(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.geocode.return_value = self._make_provider_result()
        self.service.geocode('Quadra 304', restrict_to_city=True)
        call_args = self.provider.geocode.call_args
        query = call_args[0][0]
        self.assertIn('Palmas', query)

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_result_is_cached(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.geocode.return_value = self._make_provider_result()
        self.service.geocode('Rua das Flores, 10')
        mock_cache.set.assert_called_once()

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_returns_cached_result_without_api_call(self, mock_cache):
        cached = self._make_provider_result()
        cached['provider'] = 'google'
        mock_cache.get.return_value = cached
        result = self.service.geocode('Rua das Flores, 10')
        self.provider.geocode.assert_not_called()
        self.assertIsNotNone(result)

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_restrict_fallback_when_empty(self, mock_cache):
        """If restrict_to_city returns None, retry without restriction."""
        mock_cache.get.return_value = None

        def side_effect(query, **kwargs):
            if kwargs.get('restrict_to_city', True):
                return None
            return self._make_provider_result()

        self.provider.geocode.side_effect = side_effect
        result = self.service.geocode('Rua das Flores', restrict_to_city=True)
        self.assertIsNotNone(result)
        self.assertEqual(self.provider.geocode.call_count, 2)

    @patch('apps.stores.services.geo.service.cache')
    def test_geocode_provider_exception_returns_none(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.geocode.side_effect = Exception('timeout')
        result = self.service.geocode('Rua das Flores')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# GeoService — reverse_geocode
# ---------------------------------------------------------------------------

class GeoServiceReverseGeocodeTest(TestCase):
    def setUp(self):
        self.provider = MagicMock(spec=GoogleMapsProvider)
        self.service = GeoService(provider=self.provider)

    @patch('apps.stores.services.geo.service.cache')
    def test_reverse_geocode_returns_normalized_result(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.reverse_geocode.return_value = {
            'lat': -10.184,
            'lng': -48.334,
            'formatted_address': 'Rua das Flores, Palmas',
            'place_id': None,
            'address_components': {
                'street': 'Rua das Flores',
                'city': 'Palmas',
                'state': 'Tocantins',
                'state_code': 'TO',
                'country': 'Brasil',
                'country_code': 'BR',
            },
        }
        result = self.service.reverse_geocode(-10.184, -48.334)
        self.assertIsNotNone(result)
        self.assertEqual(result['city'], 'Palmas')
        self.assertEqual(result['lat'], -10.184)

    @patch('apps.stores.services.geo.service.cache')
    def test_reverse_geocode_uses_rounded_coords_for_cache(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.reverse_geocode.return_value = None
        # Two calls with slightly different coords that round to same 4-decimal value
        self.service.reverse_geocode(-10.1840001, -48.3340001)
        self.service.reverse_geocode(-10.1840002, -48.3340002)
        # Both should share the same cache key — provider called twice (cache miss both times)
        # but the keys computed must be equal
        first_key = mock_cache.get.call_args_list[0][0][0]
        second_key = mock_cache.get.call_args_list[1][0][0]
        self.assertEqual(first_key, second_key)

    @patch('apps.stores.services.geo.service.cache')
    def test_reverse_geocode_provider_returns_none(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.reverse_geocode.return_value = None
        result = self.service.reverse_geocode(-10.0, -48.0)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# GeoService — route + haversine fallback
# ---------------------------------------------------------------------------

class GeoServiceRouteTest(TestCase):
    def setUp(self):
        self.provider = MagicMock(spec=GoogleMapsProvider)
        self.service = GeoService(provider=self.provider)
        self.origin = (-10.184, -48.334)
        self.destination = (-10.220, -48.360)

    @patch('apps.stores.services.geo.service.cache')
    def test_calculate_route_returns_normalized_result(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 6000,
            'duration_seconds': 720,
            'polyline': 'encoded_poly',
            'departure': {},
            'arrival': {},
        }
        result = self.service.calculate_route(self.origin, self.destination)
        self.assertAlmostEqual(result['distance_km'], 6.0)
        self.assertAlmostEqual(result['duration_minutes'], 12.0)
        self.assertEqual(result['polyline'], 'encoded_poly')
        self.assertFalse(result.get('fallback', False))

    @patch('apps.stores.services.geo.service.cache')
    def test_calculate_route_uses_haversine_when_provider_fails(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.side_effect = Exception('API error')
        result = self.service.calculate_route(self.origin, self.destination)
        self.assertTrue(result['fallback'])
        self.assertGreater(result['distance_km'], 0)

    @patch('apps.stores.services.geo.service.cache')
    def test_calculate_route_uses_haversine_when_provider_returns_none(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = None
        result = self.service.calculate_route(self.origin, self.destination)
        self.assertTrue(result['fallback'])

    @patch('apps.stores.services.geo.service.cache')
    def test_calculate_route_caches_result(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 5000, 'duration_seconds': 600,
            'polyline': 'p', 'departure': {}, 'arrival': {},
        }
        self.service.calculate_route(self.origin, self.destination)
        mock_cache.set.assert_called_once()

    @patch('apps.stores.services.geo.service.cache')
    def test_calculate_distance_returns_decimal(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 5000, 'duration_seconds': 600,
            'polyline': '', 'departure': {}, 'arrival': {},
        }
        dist = self.service.calculate_distance(self.origin, self.destination)
        self.assertIsInstance(dist, Decimal)
        self.assertAlmostEqual(float(dist), 5.0)


# ---------------------------------------------------------------------------
# GeoService — validate_delivery_address
# ---------------------------------------------------------------------------

class GeoServiceValidateDeliveryTest(TestCase):
    def setUp(self):
        self.provider = MagicMock(spec=GoogleMapsProvider)
        self.service = GeoService(provider=self.provider)
        self.store_loc = (-10.184, -48.334)
        self.customer_loc = (-10.200, -48.350)

    @patch('apps.stores.services.geo.service.cache')
    def test_valid_address_within_distance_and_time(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 3000, 'duration_seconds': 480,
            'polyline': 'p', 'departure': {}, 'arrival': {},
        }
        result = self.service.validate_delivery_address(
            self.store_loc, self.customer_loc, max_distance_km=10.0, max_time_minutes=20.0
        )
        self.assertTrue(result['is_valid'])
        self.assertAlmostEqual(result['distance_km'], 3.0)

    @patch('apps.stores.services.geo.service.cache')
    def test_invalid_address_exceeds_max_distance(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 25000, 'duration_seconds': 1800,
            'polyline': 'p', 'departure': {}, 'arrival': {},
        }
        result = self.service.validate_delivery_address(
            self.store_loc, self.customer_loc, max_distance_km=20.0
        )
        self.assertFalse(result['is_valid'])
        self.assertIn('área', result['message'].lower())

    @patch('apps.stores.services.geo.service.cache')
    def test_invalid_address_exceeds_max_time(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 8000, 'duration_seconds': 4000,
            'polyline': 'p', 'departure': {}, 'arrival': {},
        }
        result = self.service.validate_delivery_address(
            self.store_loc, self.customer_loc, max_distance_km=20.0, max_time_minutes=45.0
        )
        self.assertFalse(result['is_valid'])

    @patch('apps.stores.services.geo.service.cache')
    def test_returns_polyline_in_result(self, mock_cache):
        mock_cache.get.return_value = None
        self.provider.route.return_value = {
            'distance_meters': 3000, 'duration_seconds': 480,
            'polyline': 'encoded_poly', 'departure': {}, 'arrival': {},
        }
        result = self.service.validate_delivery_address(self.store_loc, self.customer_loc)
        self.assertEqual(result['polyline'], 'encoded_poly')


# ---------------------------------------------------------------------------
# GeoService — calculate_delivery_fee
# ---------------------------------------------------------------------------

def _make_store_no_coords():
    store = MagicMock()
    store.latitude = None
    store.longitude = None
    store.metadata = {}
    store.address_data = {}
    store.default_delivery_fee = Decimal('5.00')
    return store


def _make_store_with_coords(lat=-10.184, lng=-48.334):
    store = MagicMock()
    store.latitude = lat
    store.longitude = lng
    store.metadata = {}
    store.address_data = {}
    store.default_delivery_fee = Decimal('5.00')
    store.max_delivery_distance_km = 20.0
    return store


class GeoServiceDeliveryFeeTest(TestCase):
    def setUp(self):
        self.provider = MagicMock(spec=GoogleMapsProvider)
        self.service = GeoService(provider=self.provider)

    def test_no_store_coords_returns_default_fee(self):
        store = _make_store_no_coords()
        result = self.service.calculate_delivery_fee(store, customer_lat=-10.2, customer_lng=-48.35)
        self.assertEqual(result['fee'], float(store.default_delivery_fee))
        self.assertIsNone(result['distance_km'])

    @patch('apps.stores.services.geo.service.cache')
    def test_out_of_area_returns_none_fee(self, mock_cache):
        mock_cache.get.return_value = None
        store = _make_store_with_coords()
        store.max_delivery_distance_km = 5.0
        store.metadata = {}
        self.provider.route.return_value = {
            'distance_meters': 25000, 'duration_seconds': 1800,
            'polyline': '', 'departure': {}, 'arrival': {},
        }
        with patch('apps.stores.models.StoreDeliveryZone') as mock_zone_model:
            mock_zone_model.objects.filter.return_value.order_by.return_value.exists.return_value = False
            result = self.service.calculate_delivery_fee(store, customer_lat=-10.4, customer_lng=-48.5)
        self.assertFalse(result['is_within_area'])
        self.assertIsNone(result['fee'])

    @patch('apps.stores.services.geo.service.cache')
    def test_fixed_price_zone_overrides_dynamic_fee(self, mock_cache):
        mock_cache.get.return_value = None
        store = _make_store_with_coords()
        store.metadata = {
            'fixed_price_zones': [
                {'name': 'Taquaralto', 'keywords': ['taquaralto'], 'fee': '3.50'},
            ]
        }
        self.provider.route.return_value = {
            'distance_meters': 8000, 'duration_seconds': 900,
            'polyline': '', 'departure': {}, 'arrival': {},
        }
        # Reverse geocode returns neighborhood with 'taquaralto' keyword
        self.provider.reverse_geocode.return_value = {
            'lat': -10.26, 'lng': -48.33,
            'formatted_address': 'Rua Principal, Taquaralto, Palmas',
            'place_id': None,
            'address_components': {'neighborhood': 'Taquaralto', 'city': 'Palmas'},
        }
        result = self.service.calculate_delivery_fee(store, customer_lat=-10.26, customer_lng=-48.33)
        self.assertTrue(result['is_within_area'])
        self.assertEqual(float(result['fee']), 3.50)
        self.assertEqual(result['zone']['name'], 'Taquaralto')

    @patch('apps.stores.services.geo.service.cache')
    def test_delivery_zone_db_record_used_when_exists(self, mock_cache):
        mock_cache.get.return_value = None
        store = _make_store_with_coords()
        store.metadata = {}
        self.provider.route.return_value = {
            'distance_meters': 4000, 'duration_seconds': 480,
            'polyline': '', 'departure': {}, 'arrival': {},
        }
        zone = MagicMock()
        zone.matches_distance.return_value = True
        zone.calculate_fee.return_value = Decimal('6.00')
        zone.name = 'Zona 1'
        zone.id = 'zone-uuid'
        zone.min_km = 0
        zone.max_km = 5
        with patch('apps.stores.models.StoreDeliveryZone') as mock_zone_model:
            mock_zone_model.objects.filter.return_value.order_by.return_value.exists.return_value = True
            mock_zone_model.objects.filter.return_value.order_by.return_value.__iter__ = lambda self: iter([zone])
            result = self.service.calculate_delivery_fee(store, customer_lat=-10.2, customer_lng=-48.35)
        self.assertTrue(result['is_within_area'])
        self.assertEqual(float(result['fee']), 6.0)

    @patch('apps.stores.services.geo.service.cache')
    def test_no_zone_delegates_to_checkout_service_dynamic_fee(self, mock_cache):
        mock_cache.get.return_value = None
        store = _make_store_with_coords()
        store.metadata = {}
        self.provider.route.return_value = {
            'distance_meters': 3000, 'duration_seconds': 360,
            'polyline': '', 'departure': {}, 'arrival': {},
        }
        with patch('apps.stores.models.StoreDeliveryZone') as mock_zone_model:
            mock_zone_model.objects.filter.return_value.order_by.return_value.exists.return_value = False
            with patch('apps.stores.services.geo.service.GeoService._get_checkout_service_cls') as mock_cs_cls:
                mock_cs = MagicMock()
                mock_cs._calculate_dynamic_fee.return_value = {'fee': Decimal('4.50')}
                mock_cs_cls.return_value = mock_cs
                result = self.service.calculate_delivery_fee(store, customer_lat=-10.2, customer_lng=-48.35)
        self.assertTrue(result['is_within_area'])
        self.assertEqual(float(result['fee']), 4.50)
