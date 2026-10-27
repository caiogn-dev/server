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


# 19/10, Bárbara (CE-2610195503): pin CERTO na 110 Sul (ao lado da Agrovida,
# 650 m da loja), mas o texto "Av jk quadra 110 sul, Lote 21, Plano diretor
# sul" o Google devolveu como PREMISE a ~4 km — só ecoando o que foi digitado.
# O pin foi descartado e a entrega saiu R$ 14,36 (8,36 km) em vez de ~R$ 8.
# O reverso do pin dizia "110 Sul": a MESMA quadra escrita. Isso é prova.
BARBARA_PIN_CERTO = (-10.184835033183676, -48.30957419225769)
TEXTO_DA_BARBARA_ERRADO = (-10.2133048, -48.3469198)


class QuadraDoPinoTests(TestCase):
    ENDERECO = {
        'street': 'Av jk quadra 110 sul', 'number': 'Lote 21', 'neighborhood': 'Plano diretor sul ',
        'city': 'Palmas', 'state': 'Tocantins',
        'complement': 'Clínica DVI (ao lado da Agrovida pet shop)',
    }
    REVERSO_110_SUL = {
        'street': 'Quadra 110 Sul Alameda 1', 'number': '56', 'neighborhood': '110 Sul',
        'formatted_address': 'Q. 110 Sul Alameda 1, 56 - 110 Sul, Palmas - TO, 77020-142, Brasil',
    }

    def _cotar(self, reverso, endereco=None):
        from unittest.mock import patch, MagicMock
        from apps.stores.services.checkout_service import CheckoutService
        payload = {'method': 'delivery', 'lat': BARBARA_PIN_CERTO[0], 'lng': BARBARA_PIN_CERTO[1],
                   'address': endereco or self.ENDERECO}
        geo = {'lat': TEXTO_DA_BARBARA_ERRADO[0], 'lng': TEXTO_DA_BARBARA_ERRADO[1], 'location_type': 'PREMISE'}
        with patch('apps.stores.services.geo.service.GeoService.geocode', return_value=geo), \
             patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value=reverso), \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value={'success': True, 'fee': 8.0, 'distance_km': 1.9}) as calc:
            CheckoutService.calculate_delivery_fee_for_payload(MagicMock(), payload)
        return calc.call_args.kwargs

    def test_pin_na_quadra_escrita_e_mantido(self):
        kw = self._cotar(self.REVERSO_110_SUL)
        self.assertEqual((kw['lat'], kw['lng']), BARBARA_PIN_CERTO)

    def test_quadra_so_no_formatted_address_tambem_vale(self):
        kw = self._cotar({'street': 'Alameda 1', 'number': '56',
                          'formatted_address': 'Q. 110 Sul Alameda 1, 56 - 110 Sul, Palmas - TO, Brasil'})
        self.assertEqual((kw['lat'], kw['lng']), BARBARA_PIN_CERTO)

    def test_quadra_vizinha_continua_derrubada(self):
        """Simone, 01/10: escreveu 704 Sul, pin na 702 Sul — o pin estava errado."""
        kw = self._cotar(
            {'street': 'Alameda 2', 'number': '10', 'neighborhood': '702 Sul',
             'formatted_address': 'Q. 702 Sul Alameda 2, 10 - 702 Sul, Palmas - TO, Brasil'},
            endereco={**self.ENDERECO, 'street': 'Alameda 5 quadra 704 sul', 'number': '12'},
        )
        self.assertEqual((kw['lat'], kw['lng']), (None, None))

    def test_sul_e_norte_de_mesmo_numero_nao_confundem(self):
        kw = self._cotar(
            {'street': 'Alameda 1', 'number': '5', 'neighborhood': '110 Norte',
             'formatted_address': 'Q. 110 Norte Alameda 1, 5 - 110 Norte, Palmas - TO, Brasil'},
        )
        self.assertEqual((kw['lat'], kw['lng']), (None, None))

    def test_endereco_sem_quadra_nao_ganha_atalho(self):
        kw = self._cotar(self.REVERSO_110_SUL, endereco={
            'street': 'Avenida Teotônio Segurado', 'number': '1500', 'neighborhood': 'Plano Diretor Sul',
            'city': 'Palmas', 'state': 'Tocantins',
        })
        self.assertEqual((kw['lat'], kw['lng']), (None, None))


# 27/10 — Lais (CE-2610278982): pin certo na Orla 14. O texto "FIETO, 01,
# Parque" foi achado pelo NOME: o Google devolveu a OUTRA FIETO, em Taquaralto
# (PREMISE_PROXIMITY, 9,4 km). Taquaralto não aparece em nada do que ela
# escreveu — é homônimo, não prova contra o pin. Frete R$ 40 em vez de 12,58.
#
# 15/10 — CE-2610157694: escreveu "Quadra 407 norte Al 07 lote 58", pin na
# 111 Sul. O texto voltou PREMISE_PROXIMITY em "Plano Diretor Norte" — o bairro
# que ela escreveu. Ali o texto É a prova e o pin tem que cair.
LAIS_PIN = (-10.1984233, -48.3638472)
FIETO_TAQUARALTO = {
    'lat': -10.279684, 'lng': -48.3386795, 'location_type': 'PREMISE_PROXIMITY',
    'neighborhood': 'Jardim Aureny III (Taquaralto)',
    'formatted_address': 'FIETO, 01 - Jardim Aureny III (Taquaralto), Palmas - TO, Brasil',
}
LAIS_ENDERECO = {'street': 'FIETO', 'number': '01', 'neighborhood': 'Parque',
                 'city': 'Palmas', 'state': 'TO', 'zip_code': '77026035'}

PIN_111_SUL = (-10.1951, -48.3301)
TEXTO_407_NORTE = {
    'lat': -10.1713, 'lng': -48.3279, 'location_type': 'PREMISE_PROXIMITY',
    'neighborhood': 'Plano Diretor Norte',
    'formatted_address': 'Quadra 407 norte Al 07, 58 - Plano Diretor Norte, Palmas - TO, Brasil',
}
ENDERECO_407 = {'street': 'Quadra 407 norte Al 07 lote 58 casa 02', 'number': '58',
                'neighborhood': 'Plano Diretor Norte', 'city': 'Palmas', 'state': 'Tocantins'}


class TextoAchouOLugarEscritoTests(TestCase):
    def _f(self, geo, endereco):
        from apps.stores.services.coerencia_do_ponto import texto_achou_o_lugar_escrito
        return texto_achou_o_lugar_escrito(geo, endereco)

    def test_homonimo_em_outro_bairro_nao_e_prova(self):
        self.assertFalse(self._f(FIETO_TAQUARALTO, LAIS_ENDERECO))

    def test_texto_no_bairro_escrito_e_prova(self):
        self.assertTrue(self._f(TEXTO_407_NORTE, ENDERECO_407))

    def test_parte_entre_parenteses_tambem_conta(self):
        self.assertTrue(self._f(FIETO_TAQUARALTO, {**LAIS_ENDERECO, 'neighborhood': 'Taquaralto'}))

    def test_mesma_quadra_e_prova_mesmo_com_bairro_diferente(self):
        geo = {**TEXTO_407_NORTE, 'neighborhood': 'Algum Outro'}
        self.assertTrue(self._f(geo, ENDERECO_407))

    def test_sem_bairro_dos_dois_lados_continua_valendo(self):
        """Sem ter o que comparar, mantém o comportamento de antes."""
        self.assertTrue(self._f({**FIETO_TAQUARALTO, 'neighborhood': ''}, LAIS_ENDERECO))
        self.assertTrue(self._f(FIETO_TAQUARALTO, {'street': 'FIETO', 'city': 'Palmas'}))


class PedidoDaLaisTests(TestCase):
    def _cotar(self, pin, endereco, geo_do_texto):
        from unittest.mock import patch, MagicMock
        from apps.stores.services.checkout_service import CheckoutService
        payload = {'method': 'delivery', 'lat': pin[0], 'lng': pin[1], 'address': endereco}
        with patch('apps.stores.services.geo.service.GeoService.geocode', return_value=geo_do_texto), \
             patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value={}), \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value={'success': True, 'fee': 12.58, 'distance_km': 8.58}) as calc:
            CheckoutService.calculate_delivery_fee_for_payload(MagicMock(), payload)
        return calc.call_args.kwargs

    def test_homonimo_nao_derruba_o_pin(self):
        kw = self._cotar(LAIS_PIN, LAIS_ENDERECO, FIETO_TAQUARALTO)
        self.assertEqual((kw['lat'], kw['lng']), LAIS_PIN)

    def test_407_norte_continua_derrubando_o_pin_da_111_sul(self):
        kw = self._cotar(PIN_111_SUL, ENDERECO_407, TEXTO_407_NORTE)
        self.assertIsNone(kw['lat'])
