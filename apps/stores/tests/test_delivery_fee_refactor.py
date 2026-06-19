"""Testes de caracterização CORRETOS para GeoService.calculate_delivery_fee.

Os golden values aqui foram capturados do código em produção (harness diferencial
original-vs-refatorado, ambos byte-a-byte idênticos), NÃO chutados.

Fonte da verdade do cálculo dinâmico: DeliveryQuoteService.calculate_dynamic_fee
  base_fee = metadata['delivery_base_fee'] OU store.default_delivery_fee OU 9.00
  +R$1,00/km (delivery_fee_per_km) acima de 4 km (delivery_flat_km)
  > 16 km (delivery_max_km) → fee=None
  chuva → +R$2,00

Por isso a loja-fixture usa default_delivery_fee=7.50: o base dinâmico É essa taxa
(7.50), não um "R$9" hardcoded. Para 6 km: 7.50 + (6-4)*1 = 9.50.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.stores.services.geo.service import GeoService


def _make_store(**overrides):
    base = dict(
        latitude=Decimal('-10.18'), longitude=Decimal('-48.33'),
        default_delivery_fee=Decimal('7.50'),  # = base dinâmico real
        metadata={}, address_data={}, city='Palmas', state='TO',
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _route(distance_km, duration_minutes=20.0, polyline='abc'):
    return {'distance_km': distance_km, 'duration_minutes': duration_minutes, 'polyline': polyline}


class CalculateDeliveryFeeCharacterizationTests(SimpleTestCase):
    def setUp(self):
        self.geo = GeoService(provider=mock.MagicMock())
        zone_patcher = mock.patch('apps.stores.models.StoreDeliveryZone.objects')
        self.mock_zone_objects = zone_patcher.start()
        self.addCleanup(zone_patcher.stop)
        qs = mock.MagicMock()
        qs.exists.return_value = False
        self.mock_zone_objects.filter.return_value.order_by.return_value = qs

    # ── Sem coordenadas da loja → taxa padrão (= default_delivery_fee) ──────
    def test_loja_sem_coordenadas_retorna_taxa_padrao(self):
        store = _make_store(latitude=None, longitude=None)
        result = self.geo.calculate_delivery_fee(store)
        self.assertEqual(result['fee'], 7.5)
        self.assertIsNone(result['distance_km'])
        self.assertTrue(result['is_within_area'])
        self.assertIsNone(result['zone'])
        self.assertEqual(result['message'], 'Taxa de entrega padrão aplicada')

    def test_loja_sem_coordenadas_com_chuva(self):
        store = _make_store(latitude=None, longitude=None)
        result = self.geo.calculate_delivery_fee(store, rain_surcharge=True)
        self.assertEqual(result['fee'], 9.5)  # 7.50 + 2.00

    # ── Sem rota → taxa padrão, fora da área ────────────────────────────────
    def test_sem_rota_retorna_taxa_padrao_fora_area(self):
        result = self.geo.calculate_delivery_fee(_make_store())
        self.assertEqual(result['fee'], 7.5)
        self.assertFalse(result['is_within_area'])
        self.assertEqual(result['message'], 'Não foi possível geocodificar o endereço')

    # ── Dinâmico: base plana até 4 km, +R$1/km depois ───────────────────────
    def test_dinamico_dentro_flat_km(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(3.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(_make_store(), customer_lat=-10.2, customer_lng=-48.3)
        self.assertEqual(result['fee'], 7.5)
        self.assertEqual(result['message'], 'Taxa: R$ 7.50 (3.0 km)')
        self.assertTrue(result['is_within_area'])
        self.assertFalse(result['rain_surcharge_applied'])

    def test_dinamico_exatamente_flat_km(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(4.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(_make_store(), customer_lat=-10.2, customer_lng=-48.3)
        self.assertEqual(result['fee'], 7.5)

    def test_dinamico_acima_flat_km(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(6.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(_make_store(), customer_lat=-10.2, customer_lng=-48.3)
        self.assertEqual(result['fee'], 9.5)  # 7.50 + (6-4)*1
        self.assertEqual(result['message'], 'Taxa: R$ 9.50 (6.0 km)')

    def test_dinamico_tier_distante(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(10.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(_make_store(), customer_lat=-10.2, customer_lng=-48.3)
        self.assertEqual(result['fee'], 13.5)  # 7.50 + (10-4)*1

    def test_dinamico_com_chuva(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(6.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(
                _make_store(), customer_lat=-10.2, customer_lng=-48.3, rain_surcharge=True)
        self.assertEqual(result['fee'], 11.5)  # 9.50 + 2.00
        self.assertTrue(result['rain_surcharge_applied'])
        self.assertEqual(result['message'], 'Taxa: R$ 11.50 (6.0 km) + R$2,00 chuva')

    def test_dinamico_acima_max_km_retorna_none(self):
        with mock.patch.object(self.geo, '_get_route', return_value=_route(17.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone', return_value=None):
            result = self.geo.calculate_delivery_fee(_make_store(), customer_lat=-10.2, customer_lng=-48.3)
        self.assertIsNone(result['fee'])
        self.assertFalse(result['is_within_area'])

    # ── Zona fixa plana ─────────────────────────────────────────────────────
    def test_zona_fixa_plana(self):
        store = _make_store(metadata={'fixed_price_zones': [{'name': 'Taquaralto', 'fee': '40.00'}]})
        with mock.patch.object(self.geo, '_get_route', return_value=_route(8.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone',
                               return_value={'name': 'Taquaralto', 'fee': '40.00'}):
            result = self.geo.calculate_delivery_fee(store, customer_lat=-10.3, customer_lng=-48.4)
        self.assertEqual(result['fee'], 40.0)
        self.assertEqual(result['zone']['name'], 'Taquaralto')

    # ── Zona aditiva (condomínio fechado: km_fee + sobretaxa) ───────────────
    def test_zona_fixa_aditiva_surcharge_on_km(self):
        store = _make_store(metadata={'fixed_price_zones': [{'name': 'Alphaville'}]})
        with mock.patch.object(self.geo, '_get_route', return_value=_route(6.0)), \
             mock.patch.object(self.geo, '_match_fixed_price_zone',
                               return_value={'name': 'Alphaville', 'surcharge_on_km': True, 'surcharge': '5.00'}):
            result = self.geo.calculate_delivery_fee(store, customer_lat=-10.3, customer_lng=-48.4)
        self.assertEqual(result['fee'], 14.5)  # km_fee(6km)=9.50 + 5.00
        self.assertEqual(result['message'], 'Condomínio fechado: taxa por km + R$ 5.00 de acesso')
