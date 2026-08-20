"""O pin não pode contradizer o endereço escrito."""
from django.test import TestCase

from apps.stores.services.coerencia_do_ponto import (
    distancia_km, ponto_confere_com_texto, TOLERANCIA_KM,
)

# Coordenadas reais dos dois pedidos que saíram errados em 20/08.
SECRETARIA_REAL = (-10.183058, -48.336260)
YASMINE_PIN     = (-10.188394, -48.295984)
JK_110_SUL_REAL = (-10.184435, -48.310945)
BARBARA_PIN     = (-10.229895, -48.320539)


class DistanciaTests(TestCase):
    def test_mesmo_ponto_da_zero(self):
        self.assertAlmostEqual(distancia_km(-10.18, -48.33, -10.18, -48.33), 0, places=6)

    def test_bate_com_a_distancia_medida_no_google(self):
        d = distancia_km(*SECRETARIA_REAL, *YASMINE_PIN)
        self.assertAlmostEqual(d, 4.45, delta=0.15)


class PontoConfereTests(TestCase):
    def test_pedido_da_yasmine_seria_barrado(self):
        self.assertFalse(ponto_confere_com_texto(*YASMINE_PIN, *SECRETARIA_REAL))

    def test_pedido_da_barbara_seria_barrado(self):
        self.assertFalse(ponto_confere_com_texto(*BARBARA_PIN, *JK_110_SUL_REAL))

    def test_pin_no_lugar_certo_passa(self):
        """Quem está certo não pode ser punido: 200 m de diferença é normal."""
        lat, lng = SECRETARIA_REAL
        self.assertTrue(ponto_confere_com_texto(lat + 0.0018, lng, lat, lng))

    def test_sem_uma_das_pontas_nao_descarta(self):
        """Sem como comparar, manter o pin. Derrubar por falta de prova
        quebraria quem está certo."""
        self.assertTrue(ponto_confere_com_texto(-10.18, -48.33, None, None))
        self.assertTrue(ponto_confere_com_texto(None, None, -10.18, -48.33))

    def test_limite_da_tolerancia(self):
        lat, lng = SECRETARIA_REAL
        graus = TOLERANCIA_KM / 111.0
        self.assertTrue(ponto_confere_com_texto(lat + graus * 0.9, lng, lat, lng))
        self.assertFalse(ponto_confere_com_texto(lat + graus * 1.4, lng, lat, lng))
