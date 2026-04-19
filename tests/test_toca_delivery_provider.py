"""
TDD tests for TocaDeliveryProvider and delivery_provider module.

Coverage:
- TocaDeliveryProvider: auth, quote, create, cancel, get_status, token expiry
- Status mapping: CorridaStatus → StoreOrder.OrderStatus
- get_delivery_provider: selects provider by store config / settings
- InternalDeliveryProvider: no-op behaviour
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

from django.test import TestCase, override_settings

from apps.stores.services.delivery_provider import (
    InternalDeliveryProvider,
    TocaDeliveryProvider,
    get_delivery_provider,
)
from apps.stores.services.delivery_provider.base import DeliveryProviderError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_store(lat=-10.184, lng=-48.334):
    store = MagicMock()
    store.latitude = lat
    store.longitude = lng
    store.address = 'Quadra 304 Sul, Alameda 2, Lote 1'
    store.number = '1'
    store.complement = None
    store.neighborhood = 'Plano Diretor Sul'
    store.city = 'Palmas'
    store.state = 'TO'
    store.zip_code = '77016-002'
    store.metadata = {}
    store.address_data = {'lat': lat, 'lng': lng}
    return store


def _make_order(delivery_method='delivery'):
    order = MagicMock()
    order.customer_name = 'João Silva'
    order.customer_phone = '63999990000'
    order.delivery_method = delivery_method
    order.delivery_fee = Decimal('8.00')
    order.delivery_notes = ''
    order.delivery_address = {
        'street': 'Rua das Rosas',
        'number': '42',
        'complement': 'Apto 3',
        'neighborhood': 'Jardim Aureny III',
        'city': 'Palmas',
        'state': 'TO',
        'zip_code': '77064-050',
        'lat': -10.26,
        'lng': -48.33,
    }
    return order


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def _auth_response():
    return {'access_token': 'jwt.token.here', 'refresh_token': 'refresh.token', 'token_type': 'bearer'}


def _corrida_response(corrida_id='corrida-uuid-001', codigo='TCA-1234', status='criada'):
    return {
        'id': corrida_id,
        'codigo': codigo,
        'status': status,
        'tipo': 'imediata',
        'origem_endereco': {},
        'destino_endereco': {},
        'destinatario_nome': 'João Silva',
        'destinatario_tel': '63999990000',
        'observacoes': None,
        'valor_total': '8.50',
        'taxa_toca': '0.26',
        'valor_entregador': '8.24',
        'route_polyline': 'encoded_poly_abc',
        'route_distance_meters': 6500,
        'route_duration_seconds': 780,
        'created_at': '2026-04-18T10:00:00Z',
        'updated_at': '2026-04-18T10:00:00Z',
    }


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — authentication
# ---------------------------------------------------------------------------

class TocaAuthTest(TestCase):
    def _provider(self):
        return TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='test@empresa.com',
            password='s3cret',
        )

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.post')
    def test_authenticate_success_caches_token(self, mock_post, mock_cache):
        mock_cache.get.return_value = None
        mock_post.return_value = _mock_response(_auth_response())
        provider = self._provider()
        token = provider._authenticate()
        self.assertEqual(token, 'jwt.token.here')
        mock_cache.set.assert_called_once()
        args = mock_cache.set.call_args
        self.assertEqual(args[0][1], 'jwt.token.here')

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.post')
    def test_authenticate_bad_status_raises_error(self, mock_post, mock_cache):
        mock_cache.get.return_value = None
        mock_post.return_value = _mock_response({'detail': 'Unauthorized'}, status_code=401)
        provider = self._provider()
        with self.assertRaises(DeliveryProviderError):
            provider._authenticate()

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    def test_get_token_returns_cached_token(self, mock_cache):
        mock_cache.get.return_value = 'cached.jwt.token'
        provider = self._provider()
        token = provider._get_token()
        self.assertEqual(token, 'cached.jwt.token')

    def test_missing_credentials_raises_error(self):
        provider = TocaDeliveryProvider(api_url='https://api.tocadelivery.com.br', email='', password='')
        with self.assertRaises(DeliveryProviderError):
            provider._authenticate()


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — address building
# ---------------------------------------------------------------------------

class TocaAddressBuildingTest(TestCase):
    def test_build_address_maps_server2_fields(self):
        addr = {
            'street': 'Rua das Rosas',
            'number': '42',
            'complement': 'Apto 3',
            'neighborhood': 'Aureny',
            'city': 'Palmas',
            'state': 'TO',
            'zip_code': '77064-050',
            'lat': -10.26,
            'lng': -48.33,
        }
        result = TocaDeliveryProvider._build_address(addr)
        self.assertEqual(result['logradouro'], 'Rua das Rosas')
        self.assertEqual(result['numero'], '42')
        self.assertEqual(result['complemento'], 'Apto 3')
        self.assertEqual(result['bairro'], 'Aureny')
        self.assertEqual(result['lat'], -10.26)

    def test_build_address_defaults_number_to_sn(self):
        addr = {'street': 'Rua', 'neighborhood': 'Centro', 'city': 'Palmas', 'state': 'TO'}
        result = TocaDeliveryProvider._build_address(addr)
        self.assertEqual(result['numero'], 'S/N')

    def test_store_address_uses_model_fields(self):
        store = _make_store()
        result = TocaDeliveryProvider._store_address(store)
        self.assertEqual(result['logradouro'], store.address)
        self.assertEqual(result['cidade'], 'Palmas')
        self.assertAlmostEqual(result['lat'], -10.184)


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — quote
# ---------------------------------------------------------------------------

class TocaQuoteTest(TestCase):
    def _provider(self):
        return TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='e@empresa.com', password='pw',
        )

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_quote_returns_delivery_quote(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response({
            'distancia_km': 5.2,
            'valor_total': '9.50',
            'taxa_toca': '0.29',
            'valor_entregador': '9.21',
            'zona_nome': None,
        })
        store = _make_store()
        order = _make_order()
        result = self._provider().quote(store, order)
        self.assertAlmostEqual(result.distance_km, 5.2)
        self.assertEqual(result.fee, Decimal('9.50'))
        self.assertEqual(result.provider, 'toca')

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_quote_raises_on_error_status(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response({'detail': 'error'}, status_code=400)
        with self.assertRaises(DeliveryProviderError):
            self._provider().quote(_make_store(), _make_order())


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — create
# ---------------------------------------------------------------------------

class TocaCreateDeliveryTest(TestCase):
    def _provider(self):
        return TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='e@empresa.com', password='pw',
        )

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_create_delivery_success_returns_result(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response(_corrida_response(), status_code=201)
        result = self._provider().create(_make_store(), _make_order())
        self.assertEqual(result.external_id, 'corrida-uuid-001')
        self.assertEqual(result.external_code, 'TCA-1234')
        self.assertEqual(result.external_status, 'criada')
        self.assertEqual(result.polyline, 'encoded_poly_abc')

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_create_delivery_sends_correct_payload(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response(_corrida_response(), status_code=201)
        store = _make_store()
        order = _make_order()
        self._provider().create(store, order)
        sent_payload = mock_request.call_args[1]['json']
        self.assertEqual(sent_payload['destinatario_nome'], 'João Silva')
        self.assertEqual(sent_payload['destinatario_tel'], '63999990000')
        self.assertIn('destino', sent_payload)
        self.assertIn('origem', sent_payload)

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_create_delivery_raises_on_error(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response({'detail': 'unprocessable'}, status_code=422)
        with self.assertRaises(DeliveryProviderError):
            self._provider().create(_make_store(), _make_order())

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_create_delivery_reauthenticates_on_401(self, mock_request, mock_cache):
        """On 401, invalidate cached token and retry."""
        mock_cache.get.side_effect = ['old.token', 'new.token']
        responses = [
            _mock_response({'detail': 'expired'}, status_code=401),
            _mock_response(_corrida_response(), status_code=201),
        ]
        mock_request.side_effect = responses
        result = self._provider().create(_make_store(), _make_order())
        self.assertEqual(result.external_id, 'corrida-uuid-001')
        mock_cache.delete.assert_called_once()


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — cancel
# ---------------------------------------------------------------------------

class TocaCancelTest(TestCase):
    def _provider(self):
        return TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='e@empresa.com', password='pw',
        )

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_cancel_success_returns_true(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response(_corrida_response(status='cancelada'))
        result = self._provider().cancel('corrida-uuid-001', 'Pedido cancelado pelo cliente')
        self.assertTrue(result)

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_cancel_failure_returns_false(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response({'detail': 'cannot cancel'}, status_code=409)
        result = self._provider().cancel('corrida-uuid-001')
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — get_status
# ---------------------------------------------------------------------------

class TocaGetStatusTest(TestCase):
    def _provider(self):
        return TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='e@empresa.com', password='pw',
        )

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_get_status_returns_corrida_status(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response(_corrida_response(status='em_rota'))
        status = self._provider().get_status('corrida-uuid-001')
        self.assertEqual(status, 'em_rota')

    @patch('apps.stores.services.delivery_provider.toca_delivery.cache')
    @patch('apps.stores.services.delivery_provider.toca_delivery.requests.request')
    def test_get_status_not_found_returns_none(self, mock_request, mock_cache):
        mock_cache.get.return_value = 'cached.token'
        mock_request.return_value = _mock_response({'detail': 'not found'}, status_code=404)
        status = self._provider().get_status('nonexistent-uuid')
        self.assertIsNone(status)


# ---------------------------------------------------------------------------
# TocaDeliveryProvider — status mapping
# ---------------------------------------------------------------------------

class TocaStatusMappingTest(TestCase):
    def setUp(self):
        self.provider = TocaDeliveryProvider(
            api_url='https://api.tocadelivery.com.br',
            email='e@empresa.com', password='pw',
        )

    def test_aceita_maps_to_out_for_delivery(self):
        self.assertEqual(self.provider.map_status_to_order('aceita'), 'out_for_delivery')

    def test_em_coleta_maps_to_out_for_delivery(self):
        self.assertEqual(self.provider.map_status_to_order('em_coleta'), 'out_for_delivery')

    def test_coletada_maps_to_out_for_delivery(self):
        self.assertEqual(self.provider.map_status_to_order('coletada'), 'out_for_delivery')

    def test_em_rota_maps_to_out_for_delivery(self):
        self.assertEqual(self.provider.map_status_to_order('em_rota'), 'out_for_delivery')

    def test_entregue_maps_to_delivered(self):
        self.assertEqual(self.provider.map_status_to_order('entregue'), 'delivered')

    def test_criada_maps_to_none(self):
        self.assertIsNone(self.provider.map_status_to_order('criada'))

    def test_ofertada_maps_to_none(self):
        self.assertIsNone(self.provider.map_status_to_order('ofertada'))

    def test_cancelada_maps_to_none(self):
        # Cancellation requires human review — no auto status transition
        self.assertIsNone(self.provider.map_status_to_order('cancelada'))

    def test_unknown_status_maps_to_none(self):
        self.assertIsNone(self.provider.map_status_to_order('xyzxyz'))


# ---------------------------------------------------------------------------
# InternalDeliveryProvider
# ---------------------------------------------------------------------------

class InternalDeliveryProviderTest(TestCase):
    def setUp(self):
        self.provider = InternalDeliveryProvider()

    def test_name_is_internal(self):
        self.assertEqual(self.provider.name, 'internal')

    def test_quote_returns_order_delivery_fee(self):
        order = _make_order()
        quote = self.provider.quote(_make_store(), order)
        self.assertEqual(quote.fee, Decimal('8.00'))

    def test_create_returns_empty_result(self):
        result = self.provider.create(_make_store(), _make_order())
        self.assertEqual(result.external_id, '')
        self.assertEqual(result.external_status, 'internal')

    def test_cancel_always_returns_true(self):
        self.assertTrue(self.provider.cancel('any-id'))

    def test_get_status_returns_none(self):
        self.assertIsNone(self.provider.get_status('any-id'))

    def test_map_status_to_order_returns_none(self):
        self.assertIsNone(self.provider.map_status_to_order('anything'))


# ---------------------------------------------------------------------------
# get_delivery_provider factory
# ---------------------------------------------------------------------------

class GetDeliveryProviderTest(TestCase):
    def test_returns_internal_by_default(self):
        store = _make_store()
        store.metadata = {}
        with override_settings(TOCA_DELIVERY_ENABLED=False):
            provider = get_delivery_provider(store)
        self.assertIsInstance(provider, InternalDeliveryProvider)

    def test_returns_toca_when_enabled_globally(self):
        store = _make_store()
        store.metadata = {}
        with override_settings(TOCA_DELIVERY_ENABLED=True, TOCA_DELIVERY_EMAIL='e@e.com', TOCA_DELIVERY_PASSWORD='pw', TOCA_DELIVERY_API_URL='https://api.tocadelivery.com.br'):
            provider = get_delivery_provider(store)
        self.assertIsInstance(provider, TocaDeliveryProvider)

    def test_returns_toca_when_store_metadata_says_toca(self):
        store = _make_store()
        store.metadata = {'delivery_provider': 'toca'}
        with override_settings(TOCA_DELIVERY_ENABLED=False, TOCA_DELIVERY_EMAIL='e@e.com', TOCA_DELIVERY_PASSWORD='pw', TOCA_DELIVERY_API_URL='https://api.tocadelivery.com.br'):
            provider = get_delivery_provider(store)
        self.assertIsInstance(provider, TocaDeliveryProvider)

    def test_returns_internal_when_store_metadata_not_toca(self):
        store = _make_store()
        store.metadata = {'delivery_provider': 'internal'}
        with override_settings(TOCA_DELIVERY_ENABLED=False):
            provider = get_delivery_provider(store)
        self.assertIsInstance(provider, InternalDeliveryProvider)

    def test_works_with_no_store_argument(self):
        with override_settings(TOCA_DELIVERY_ENABLED=False):
            provider = get_delivery_provider()
        self.assertIsInstance(provider, InternalDeliveryProvider)
