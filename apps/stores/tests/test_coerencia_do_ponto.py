"""Régua de distância e precisão de geocode.

A trava pino × texto foi removida em 19/11 (o pino manda) — ver
`test_pino_manda.py`. Aqui ficam só as duas peças que outros usam.
"""
from django.test import TestCase

from apps.stores.services.coerencia_do_ponto import distancia_km, geocode_e_preciso

SECRETARIA_REAL = (-10.183058, -48.336260)
YASMINE_PIN = (-10.188394, -48.295984)


class DistanciaTests(TestCase):
    def test_mesmo_ponto_da_zero(self):
        self.assertAlmostEqual(distancia_km(-10.18, -48.33, -10.18, -48.33), 0, places=6)

    def test_bate_com_a_distancia_medida_no_google(self):
        d = distancia_km(*SECRETARIA_REAL, *YASMINE_PIN)
        self.assertAlmostEqual(d, 4.45, delta=0.15)


class GeocodePrecisoTests(TestCase):
    def test_centro_generico_nao_e_endereco(self):
        self.assertFalse(geocode_e_preciso({'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'OTHER'}))
        self.assertFalse(geocode_e_preciso({'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'APPROXIMATE'}))

    def test_rua_e_endereco_servem(self):
        for tipo in ('ROUTE', 'GEOMETRIC_CENTER', 'PREMISE_PROXIMITY', 'ROOFTOP', 'RANGE_INTERPOLATED'):
            self.assertTrue(geocode_e_preciso({'lat': -10.18, 'lng': -48.31, 'location_type': tipo}), tipo)

    def test_sem_resultado_nao_e_preciso(self):
        self.assertFalse(geocode_e_preciso(None))
        self.assertFalse(geocode_e_preciso({}))
