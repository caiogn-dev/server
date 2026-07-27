"""
Testes de regressão para StoreDeliveryZone — contratos dos métodos do modelo.

O CLAUDE.md define que as regras de entrega devem ser verdade única do backend;
estes testes pinnam os contratos para prevenir regressões silenciosas nos
cálculos canônicos de taxa de entrega.

Cobre:
- get_distance_range: banda nomeada → (min, max); range custom; ausência → (None, None)
- matches_distance: inclusivo no mínimo, exclusivo no máximo, sem range → False
- matches_zip_code: range de CEP, fronteiras, strip de hífen, sem range → False
- calculate_fee: taxa plana, per_km, min_fee, combinados, tipo Decimal garantido

Todos SimpleTestCase — sem Docker/PostgreSQL.
Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
  python manage.py test apps.stores.tests.test_delivery_zone_model_contract -v 2
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.stores.models.delivery import StoreDeliveryZone


def _zone(**kwargs):
    """Constrói StoreDeliveryZone em memória (sem salvar) com defaults seguros."""
    defaults = dict(
        delivery_fee=Decimal('5.00'),
        min_fee=None,
        fee_per_km=None,
        distance_band=None,
        min_km=None,
        max_km=None,
        zip_code_start=None,
        zip_code_end=None,
    )
    defaults.update(kwargs)
    zone = StoreDeliveryZone.__new__(StoreDeliveryZone)
    for key, val in defaults.items():
        setattr(zone, key, val)
    return zone


class TestGetDistanceRange(SimpleTestCase):
    """get_distance_range: banda → intervalo; custom; ausência → (None, None)."""

    def test_banda_0_2(self):
        self.assertEqual(
            _zone(distance_band='0_2').get_distance_range(),
            (Decimal('0.00'), Decimal('2.00')),
        )

    def test_banda_2_5(self):
        self.assertEqual(
            _zone(distance_band='2_5').get_distance_range(),
            (Decimal('2.00'), Decimal('5.00')),
        )

    def test_banda_8_12(self):
        self.assertEqual(
            _zone(distance_band='8_12').get_distance_range(),
            (Decimal('8.00'), Decimal('12.00')),
        )

    def test_banda_30_plus(self):
        self.assertEqual(
            _zone(distance_band='30_plus').get_distance_range(),
            (Decimal('30.00'), Decimal('999.00')),
        )

    def test_banda_desconhecida_retorna_none(self):
        self.assertEqual(
            _zone(distance_band='99_100').get_distance_range(),
            (None, None),
        )

    def test_range_customizado(self):
        self.assertEqual(
            _zone(min_km=Decimal('3.5'), max_km=Decimal('8.0')).get_distance_range(),
            (Decimal('3.5'), Decimal('8.0')),
        )

    def test_sem_banda_sem_custom_retorna_none(self):
        self.assertEqual(_zone().get_distance_range(), (None, None))


class TestMatchesDistance(SimpleTestCase):
    """matches_distance: mínimo inclusivo, máximo exclusivo, sem range → False."""

    def test_dentro_da_banda(self):
        self.assertTrue(_zone(distance_band='0_2').matches_distance(1.0))
        self.assertTrue(_zone(distance_band='0_2').matches_distance(1.99))

    def test_limite_inferior_inclusivo(self):
        self.assertTrue(_zone(distance_band='0_2').matches_distance(0.0))
        # banda 2_5 começa exatamente em 2.0
        self.assertTrue(_zone(distance_band='2_5').matches_distance(2.0))

    def test_limite_superior_exclusivo(self):
        self.assertFalse(_zone(distance_band='0_2').matches_distance(2.0))
        self.assertFalse(_zone(distance_band='2_5').matches_distance(5.0))

    def test_fora_da_banda(self):
        self.assertFalse(_zone(distance_band='0_2').matches_distance(3.0))

    def test_banda_30_plus_aceita_distancias_grandes(self):
        zone = _zone(distance_band='30_plus')
        self.assertTrue(zone.matches_distance(30.0))
        self.assertTrue(zone.matches_distance(200.0))
        # 999 km é o teto interno da banda; testa que ainda match
        self.assertTrue(zone.matches_distance(998.0))

    def test_range_custom_match(self):
        zone = _zone(min_km=Decimal('3.0'), max_km=Decimal('7.0'))
        self.assertTrue(zone.matches_distance(3.0))
        self.assertTrue(zone.matches_distance(6.99))
        self.assertFalse(zone.matches_distance(7.0))
        self.assertFalse(zone.matches_distance(2.99))

    def test_sem_range_retorna_false(self):
        self.assertFalse(_zone().matches_distance(1.0))
        self.assertFalse(_zone().matches_distance(0.0))


class TestMatchesZipCode(SimpleTestCase):
    """matches_zip_code: range de CEP, fronteiras, strip de hífen, sem range → False."""

    def test_cep_dentro_do_range(self):
        zone = _zone(zip_code_start='01000', zip_code_end='01999')
        self.assertTrue(zone.matches_zip_code('01500'))

    def test_limite_inferior_inclusivo(self):
        zone = _zone(zip_code_start='01000', zip_code_end='01999')
        self.assertTrue(zone.matches_zip_code('01000'))

    def test_limite_superior_inclusivo(self):
        zone = _zone(zip_code_start='01000', zip_code_end='01999')
        self.assertTrue(zone.matches_zip_code('01999'))

    def test_cep_abaixo_do_range(self):
        zone = _zone(zip_code_start='01000', zip_code_end='01999')
        self.assertFalse(zone.matches_zip_code('00999'))

    def test_cep_acima_do_range(self):
        zone = _zone(zip_code_start='01000', zip_code_end='01999')
        self.assertFalse(zone.matches_zip_code('02000'))

    def test_cep_com_hifen_aceito(self):
        zone = _zone(zip_code_start='01000000', zip_code_end='01999999')
        self.assertTrue(zone.matches_zip_code('01500-000'))

    def test_cep_com_ponto_aceito(self):
        zone = _zone(zip_code_start='01000000', zip_code_end='01999999')
        self.assertTrue(zone.matches_zip_code('01.500.000'))

    def test_sem_range_retorna_false(self):
        self.assertFalse(_zone().matches_zip_code('01500'))

    def test_apenas_start_sem_end_retorna_false(self):
        self.assertFalse(_zone(zip_code_start='01000').matches_zip_code('01500'))

    def test_apenas_end_sem_start_retorna_false(self):
        self.assertFalse(_zone(zip_code_end='01999').matches_zip_code('01500'))


class TestCalculateFee(SimpleTestCase):
    """calculate_fee: taxa plana, per_km, min_fee, combinações, tipo Decimal."""

    def test_taxa_plana(self):
        self.assertEqual(_zone(delivery_fee=Decimal('8.00')).calculate_fee(), Decimal('8.00'))

    def test_per_km_adiciona_ao_base(self):
        zone = _zone(delivery_fee=Decimal('5.00'), fee_per_km=Decimal('2.00'))
        # 5.00 + 3 * 2.00 = 11.00
        self.assertEqual(zone.calculate_fee(distance_km=3), Decimal('11.00'))

    def test_per_km_sem_distancia_usa_base(self):
        zone = _zone(delivery_fee=Decimal('5.00'), fee_per_km=Decimal('2.00'))
        self.assertEqual(zone.calculate_fee(), Decimal('5.00'))

    def test_per_km_com_distancia_zero_usa_base(self):
        # distance_km=0 é falsy → fee_per_km não aplica
        zone = _zone(delivery_fee=Decimal('5.00'), fee_per_km=Decimal('2.00'))
        self.assertEqual(zone.calculate_fee(distance_km=0), Decimal('5.00'))

    def test_sem_fee_per_km_distancia_irrelevante(self):
        zone = _zone(delivery_fee=Decimal('8.00'), fee_per_km=None)
        self.assertEqual(zone.calculate_fee(distance_km=100), Decimal('8.00'))

    def test_min_fee_aplicada_quando_abaixo(self):
        zone = _zone(delivery_fee=Decimal('3.00'), min_fee=Decimal('7.00'))
        self.assertEqual(zone.calculate_fee(), Decimal('7.00'))

    def test_min_fee_nao_aplicada_quando_acima(self):
        zone = _zone(delivery_fee=Decimal('10.00'), min_fee=Decimal('7.00'))
        self.assertEqual(zone.calculate_fee(), Decimal('10.00'))

    def test_per_km_e_min_fee_min_vence(self):
        # base=2, per_km=1, 3km → 5.00; min_fee=6 → 6.00
        zone = _zone(delivery_fee=Decimal('2.00'), fee_per_km=Decimal('1.00'), min_fee=Decimal('6.00'))
        self.assertEqual(zone.calculate_fee(distance_km=3), Decimal('6.00'))

    def test_per_km_e_min_fee_km_vence(self):
        # base=2, per_km=1, 10km → 12.00; min_fee=6 → 12.00
        zone = _zone(delivery_fee=Decimal('2.00'), fee_per_km=Decimal('1.00'), min_fee=Decimal('6.00'))
        self.assertEqual(zone.calculate_fee(distance_km=10), Decimal('12.00'))

    def test_resultado_e_decimal_nao_float(self):
        result = _zone(delivery_fee=Decimal('5.00')).calculate_fee()
        self.assertIsInstance(result, Decimal)

    def test_resultado_com_per_km_e_decimal(self):
        zone = _zone(delivery_fee=Decimal('5.00'), fee_per_km=Decimal('1.50'))
        result = zone.calculate_fee(distance_km=3)
        self.assertIsInstance(result, Decimal)
        self.assertEqual(result, Decimal('9.50'))  # 5.00 + 3 * 1.50
