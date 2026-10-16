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


# 05/10 — Ana (CE-2610056624): pin certo na Praça dos Girassóis, texto
# "Praça dos Girassóis, S/n, Marco Central". O Google não acha o texto e
# devolve o "centro de Palmas" (granularidade OTHER/APPROXIMATE), a 7 km.
# A checagem trocou o pin certo por esse ponto genérico: 9,29 km, R$ 15,29.
ANA_PIN = (-10.187529710751063, -48.33630812568052)
CENTRO_GENERICO_DE_PALMAS = (-10.249091, -48.3242858)


class GeocodePrecisoTests(TestCase):
    def test_centro_generico_nao_serve_de_prova(self):
        from apps.stores.services.coerencia_do_ponto import geocode_e_preciso
        self.assertFalse(geocode_e_preciso({'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'OTHER'}))
        self.assertFalse(geocode_e_preciso({'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'APPROXIMATE'}))

    def test_rua_e_endereco_servem(self):
        """Barbara: 'Av JK 110 Sul' volta como ROUTE e continua derrubando o pin."""
        from apps.stores.services.coerencia_do_ponto import geocode_e_preciso
        for tipo in ('ROUTE', 'GEOMETRIC_CENTER', 'PREMISE_PROXIMITY', 'ROOFTOP', 'RANGE_INTERPOLATED'):
            self.assertTrue(geocode_e_preciso({'lat': -10.18, 'lng': -48.31, 'location_type': tipo}), tipo)

    def test_sem_resultado_nao_e_preciso(self):
        from apps.stores.services.coerencia_do_ponto import geocode_e_preciso
        self.assertFalse(geocode_e_preciso(None))
        self.assertFalse(geocode_e_preciso({}))


class PedidoDaAnaTests(TestCase):
    """O frete tem que sair pelo pin quando o texto só achou 'Palmas'."""

    def _cotar(self, geo_do_texto):
        from unittest.mock import patch, MagicMock
        from apps.stores.services.checkout_service import CheckoutService
        payload = {
            'method': 'delivery',
            'lat': ANA_PIN[0], 'lng': ANA_PIN[1],
            'address': {'street': 'Praça dos Girassóis', 'number': 'S/n',
                        'neighborhood': 'Marco Central', 'city': 'Palmas', 'state': 'Tocantins'},
        }
        with patch('apps.stores.services.geo.service.GeoService.geocode', return_value=geo_do_texto), \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value={'success': True, 'fee': 10.5, 'distance_km': 4.5}) as calc:
            CheckoutService.calculate_delivery_fee_for_payload(MagicMock(), payload)
        return calc.call_args.kwargs

    def test_texto_impreciso_mantem_o_pin(self):
        kw = self._cotar({'lat': CENTRO_GENERICO_DE_PALMAS[0], 'lng': CENTRO_GENERICO_DE_PALMAS[1],
                          'location_type': 'OTHER'})
        self.assertEqual((kw['lat'], kw['lng']), ANA_PIN)

    def test_texto_preciso_longe_ainda_derruba_o_pin(self):
        kw = self._cotar({'lat': CENTRO_GENERICO_DE_PALMAS[0], 'lng': CENTRO_GENERICO_DE_PALMAS[1],
                          'location_type': 'ROUTE'})
        self.assertIsNone(kw['lat'])


# 16/10 — Ana Loyse (CE-2610162865): pin certo na UFT. O texto do pedido É o
# que o Google devolve para esse pin ("Av. NS 15, 109 - Plano Diretor Norte"),
# mas o mesmo texto geocodificado de volta vira "Av. NS-03, 15-109", a 2 km.
# O pin certo foi descartado e o frete saiu pelo ponto errado (R$ 11,93 em vez
# de R$ 14,26). Se o pin cai NA rua e número escritos, ele é a prova.
UFT_PIN = (-10.177921333405909, -48.3607097581473)
NS03_ERRADO = (-10.1766552, -48.3426407)


class PedidoDaAnaLoyseTests(TestCase):
    ENDERECO = {'street': 'Avenida NS 15', 'number': '109', 'neighborhood': 'Plano Diretor Norte',
                'city': 'Palmas', 'state': 'Tocantins', 'complement': 'Residencial Rio Negro'}

    def _cotar(self, reverso, endereco=None):
        from unittest.mock import patch, MagicMock
        from apps.stores.services.checkout_service import CheckoutService
        payload = {'method': 'delivery', 'lat': UFT_PIN[0], 'lng': UFT_PIN[1],
                   'address': endereco or self.ENDERECO}
        geo_do_texto = {'lat': NS03_ERRADO[0], 'lng': NS03_ERRADO[1], 'location_type': 'ROOFTOP'}
        with patch('apps.stores.services.geo.service.GeoService.geocode', return_value=geo_do_texto), \
             patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value=reverso), \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value={'success': True, 'fee': 14.26, 'distance_km': 8.26}) as calc:
            CheckoutService.calculate_delivery_fee_for_payload(MagicMock(), payload)
        return calc.call_args.kwargs

    def test_pin_que_cai_na_rua_e_numero_escritos_e_mantido(self):
        kw = self._cotar({'street': 'Avenida NS 15', 'number': '109',
                          'formatted_address': 'Av. NS 15, 109 - Plano Diretor Norte, Palmas - TO, Brasil'})
        self.assertEqual((kw['lat'], kw['lng']), UFT_PIN)

    def test_av_abreviada_tambem_confere(self):
        kw = self._cotar({'street': 'Av. NS 15', 'number': '109'})
        self.assertEqual((kw['lat'], kw['lng']), UFT_PIN)

    def test_pin_em_outra_rua_continua_derrubado(self):
        kw = self._cotar({'street': 'Quadra 106 Norte Alameda 1', 'number': '01'})
        self.assertIsNone(kw['lat'])

    def test_mesma_rua_numero_diferente_continua_derrubado(self):
        """Avenida comprida: estar na NS 15 não basta, o número tem que bater."""
        kw = self._cotar({'street': 'Avenida NS 15', 'number': '900'})
        self.assertIsNone(kw['lat'])

    def test_sem_reverso_continua_derrubado(self):
        kw = self._cotar(None)
        self.assertIsNone(kw['lat'])
