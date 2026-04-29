"""
Testes: unificação de cálculo de taxa de entrega e correção de StoreValidateDeliveryView.

Cobertura:
1. HereMapsService.calculate_delivery_fee delega a CheckoutService._calculate_dynamic_fee
2. Ambos produzem a mesma taxa para distância idêntica (não divergem)
3. StoreValidateDeliveryView.post() usa store.latitude/longitude/metadata (não variáveis locais)
4. StoreValidateDeliveryView.post() usa o geo service unificado para respeitar zonas fixas
5. CheckoutService._calculate_dynamic_fee respeita base_fee, per_km, free_km, max_fee

Executar:
    python manage.py test tests.test_delivery_pricing_unified --keepdb -v 2
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.stores.models import Store
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.geo.service import GeoService

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass',
    )


def _make_store(owner, slug='fee-test', metadata=None, lat='0.0', lng='0.0'):
    return Store.objects.create(
        owner=owner,
        name='Fee Test Store',
        slug=slug,
        is_active=True,
        status='active',
        default_delivery_fee=Decimal('8.00'),
        latitude=lat,
        longitude=lng,
        metadata=metadata or {},
    )


# ─── Testes: CheckoutService._calculate_dynamic_fee ──────────────────────────

class DynamicFeeCalculationTest(TestCase):
    """
    Valida a fórmula: base + max(0, distance - free_km) * per_km, capped at max_fee.
    """

    def setUp(self):
        owner = _make_user('fee_owner')
        self.store = _make_store(
            owner,
            slug='fee-calc-store',
            metadata={
                'delivery_base_fee': '5.00',
                'delivery_fee_per_km': '2.00',
                'delivery_free_km': '3.0',
                'delivery_max_fee': '20.00',
            },
        )

    def test_within_free_km_returns_base_fee(self):
        result = CheckoutService._calculate_dynamic_fee(self.store, Decimal('2.0'))
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('5.00'))

    def test_exactly_at_free_km_threshold_returns_base(self):
        result = CheckoutService._calculate_dynamic_fee(self.store, Decimal('3.0'))
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('5.00'))

    def test_extra_km_adds_per_km_rate(self):
        # 5 km → 3 free → 2 extra × R$2.00 = R$4.00 → total R$9.00
        result = CheckoutService._calculate_dynamic_fee(self.store, Decimal('5.0'))
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('9.00'))

    def test_fee_capped_at_max_fee(self):
        # 20 km → far over threshold; without cap = 5 + 17*2 = 39 → capped at 20
        result = CheckoutService._calculate_dynamic_fee(self.store, Decimal('20.0'))
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('20.00'))

    def test_no_distance_returns_base_fee(self):
        result = CheckoutService._calculate_dynamic_fee(self.store, None)
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('5.00'))

    def test_uses_store_default_delivery_fee_as_base_when_no_metadata(self):
        owner = _make_user('fee_default_owner')
        store = _make_store(owner, slug='fee-default-store')  # no metadata overrides
        result = CheckoutService._calculate_dynamic_fee(store, Decimal('1.0'))
        # default_delivery_fee = 8.00, distance=1 <= free_km(3) → base fee
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('8.00'))


class DynamicDeliveryAreaPolicyTest(TestCase):
    def setUp(self):
        owner = _make_user('area_policy_owner')
        self.store = _make_store(
            owner,
            slug='area-policy-store',
            lat='-10.1853248',
            lng='-48.3037058',
            metadata={
                'delivery_base_fee': '9.00',
                'delivery_fee_per_km': '1.00',
                'delivery_flat_km': '4.0',
                'dynamic_delivery_area_label': 'Plano Diretor Norte/Sul',
                'dynamic_delivery_area_keywords': [
                    'plano diretor sul', 'plano diretor norte',
                    'arse', 'arso', 'acsu', 'acno', 'arne', 'arno',
                ],
                'fixed_price_zones': [
                    {'name': 'Taquaralto', 'fee': 45, 'keywords': ['taquaralto']},
                    {'name': 'Taquari', 'fee': 45, 'keywords': ['taquari']},
                    {'name': 'Santa Bárbara', 'fee': 45, 'keywords': ['santa barbara', 'santa bárbara']},
                    {'name': 'Bertaville', 'fee': 45, 'keywords': ['bertaville']},
                ],
            },
        )
        self.service = GeoService()

    def test_plano_diretor_address_uses_dynamic_fee(self):
        with patch.object(self.service, '_get_route', return_value={
            'distance_km': 6.31,
            'duration_minutes': 11.2,
            'polyline': '',
        }), patch.object(self.service, 'reverse_geocode', return_value={
            'neighborhood': 'Arse',
            'formatted_address': 'Q. 404 Sul Alameda 3, Arse, Palmas - TO',
        }):
            result = self.service.calculate_delivery_fee(
                self.store,
                customer_lat=-10.2054738,
                customer_lng=-48.3295824,
                customer_address_text='Q. 404 Sul Alameda 3, Plano Diretor Sul',
            )

        self.assertTrue(result['is_within_area'])
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('11.31'))

    def test_fixed_taquaralto_overrides_dynamic_area_restriction(self):
        with patch.object(self.service, '_get_route', return_value={
            'distance_km': 12.0,
            'duration_minutes': 25,
            'polyline': '',
        }), patch.object(self.service, 'reverse_geocode', return_value={
            'neighborhood': 'Taquaralto',
            'formatted_address': 'Taquaralto, Palmas - TO',
        }):
            result = self.service.calculate_delivery_fee(
                self.store,
                customer_lat=-10.30,
                customer_lng=-48.30,
                customer_address_text='Taquaralto',
            )

        self.assertTrue(result['is_within_area'])
        self.assertEqual(Decimal(str(result['fee'])).quantize(Decimal('0.01')), Decimal('45.00'))
        self.assertEqual(result['zone']['name'], 'Taquaralto')

    def test_non_fixed_area_outside_plano_diretor_is_not_dynamic(self):
        with patch.object(self.service, '_get_route', return_value={
            'distance_km': 8.0,
            'duration_minutes': 18,
            'polyline': '',
        }), patch.object(self.service, 'reverse_geocode', return_value={
            'neighborhood': 'Aeroporto',
            'formatted_address': 'Aeroporto, Palmas - TO',
        }):
            result = self.service.calculate_delivery_fee(
                self.store,
                customer_lat=-10.24,
                customer_lng=-48.35,
                customer_address_text='Aeroporto',
            )

        self.assertFalse(result['is_within_area'])
        self.assertIsNone(result['fee'])
        self.assertEqual(result['reason'], 'outside_dynamic_delivery_area')


# ─── Testes: HereMapsService delega a CheckoutService ────────────────────────

class HereMapsServiceDelegatesTest(TestCase):
    """
    Garante que calculate_delivery_fee chama CheckoutService._calculate_dynamic_fee
    ao invés de recalcular inline — prevenindo divergência de valores.
    """

    def setUp(self):
        owner = _make_user('maps_delegate_owner')
        self.store = _make_store(owner, slug='maps-delegate-store', lat='-10.18', lng='-48.33')

    def test_calculate_delivery_fee_delegates_to_checkout_service(self):
        from apps.stores.services.here_maps_service import HereMapsService

        mock_route = {
            'distance_km': 5.0,
            'duration_minutes': 15,
            'polyline': None,
        }

        with patch.object(
            HereMapsService, '_get_route', return_value=mock_route
        ), patch(
            'apps.stores.services.checkout_service.CheckoutService._calculate_dynamic_fee',
            return_value={'fee': Decimal('9.00'), 'zone_name': 'Padrao', 'estimated_minutes': 20, 'estimated_days': 0},
        ) as mock_calc:
            svc = HereMapsService()
            result = svc.calculate_delivery_fee(
                store=self.store,
                destination_address='Rua Teste, 10',
            )

        mock_calc.assert_called_once()
        self.assertEqual(result['fee'], Decimal('9.00'))

    def test_here_and_checkout_produce_same_fee_for_same_distance(self):
        """
        Integração: ambos os serviços calculam a mesma taxa para distância idêntica.
        Evita regressão onde fórmulas divergentes geram valores diferentes.
        """
        owner = _make_user('parity_owner')
        store = _make_store(
            owner,
            slug='fee-parity-store',
            lat='-10.18', lng='-48.33',
            metadata={'delivery_base_fee': '5.00', 'delivery_fee_per_km': '2.00',
                      'delivery_free_km': '3.0', 'delivery_max_fee': '20.00'},
        )
        distance = Decimal('6.0')

        checkout_result = CheckoutService._calculate_dynamic_fee(store, distance)
        checkout_fee = Decimal(str(checkout_result['fee'])).quantize(Decimal('0.01'))

        mock_route = {'distance_km': float(distance), 'duration_minutes': 18, 'polyline': None}
        with patch(
            'apps.stores.services.here_maps_service.HereMapsService._get_route',
            return_value=mock_route,
        ):
            from apps.stores.services.here_maps_service import HereMapsService
            here_result = HereMapsService().calculate_delivery_fee(
                store=store, destination_address='Rua Teste, 1'
            )

        here_fee = Decimal(str(here_result['fee'])).quantize(Decimal('0.01'))
        self.assertEqual(checkout_fee, here_fee,
                         f"Fee divergence: CheckoutService={checkout_fee}, HereMapsService={here_fee}")


# ─── Testes: StoreValidateDeliveryView ───────────────────────────────────────

class StoreValidateDeliveryViewTest(TestCase):
    """
    Garante que a view usa store.latitude, store.longitude e store.metadata
    (não variáveis locais indefinidas que causariam NameError em produção).
    """

    def setUp(self):
        self.owner = _make_user('vdv_owner')
        self.store = _make_store(
            self.owner,
            slug='vdv-store',
            lat='-10.184',
            lng='-48.334',
            metadata={'max_delivery_distance_km': '15'},
        )
        self.client = Client()
        self.client.force_login(self.owner)

    def test_post_with_address_does_not_crash_with_nameerror(self):
        """
        Antes do fix: NameError em store_lat/store_lng.
        Após o fix: a view deve retornar 200 ou 400 (nunca 500).
        """
        mock_geo = {
            'lat': -10.20, 'lng': -48.35,
            'distance_km': 3.0,
            'duration_minutes': 10,
            'address_components': {'city': 'Palmas'},
        }
        with patch(
            'apps.stores.api.maps_views.here_maps_service.calculate_delivery_fee',
            return_value={
                'fee': Decimal('8.00'),
                'distance_km': 3.0,
                'duration_minutes': 10,
                'is_within_area': True,
                'zone': None,
                'message': 'ok',
            },
        ), patch(
            'apps.stores.api.maps_views.here_maps_service.geocode',
            return_value=mock_geo,
        ):
            response = self.client.post(
                f'/api/v1/stores/{self.store.slug}/maps/validate-delivery/',
                data={'address': 'Rua Teste, 10'},
                content_type='application/json',
            )

        self.assertNotEqual(response.status_code, 500,
                            "View returned 500 — possible NameError in store coordinates")
        self.assertIn(response.status_code, [200, 400, 404])

    def test_post_uses_unified_geo_fee_calculation(self):
        with patch(
            'apps.stores.api.maps_views.here_maps_service.validate_delivery_address',
            return_value={
                'is_valid': True,
                'distance_km': 12.4,
                'duration_minutes': 27,
                'message': 'ok',
            },
        ), patch(
            'apps.stores.api.maps_views.here_maps_service.calculate_delivery_fee',
            return_value={
                'fee': Decimal('45.00'),
                'distance_km': 12.4,
                'duration_minutes': 27,
                'is_within_area': True,
                'zone': {'name': 'Taquaralto'},
                'message': 'Entrega com taxa fixa para a região: Taquaralto',
            },
        ) as mock_geo_fee, patch(
            'apps.stores.services.checkout_service.CheckoutService.calculate_delivery_fee'
        ) as legacy_fee:
            response = self.client.post(
                f'/api/v1/stores/{self.store.slug}/validate-delivery/',
                data={'lat': -10.26, 'lng': -48.33},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.json()['delivery_fee'])).quantize(Decimal('0.01')), Decimal('45.00'))
        self.assertEqual(response.json()['delivery_zone'], 'Taquaralto')
        mock_geo_fee.assert_called_once()
        legacy_fee.assert_not_called()
