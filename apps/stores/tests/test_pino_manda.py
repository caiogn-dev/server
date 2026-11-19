"""O pino marcado no mapa é o endereço de entrega. Ponto.

Dono, 19/11 (Emmanuel, CE-2611190382, R$ 40 de frete a 6,75 km): "quero que
seja o pino onde está marcando no mapa, apenas".

O que dava errado, em duas camadas:

1. A "trava de coerência" geocodificava o TEXTO e, se o ponto do texto ficasse
   longe do pino, jogava o pino fora. O Google pôs "ACSU SO 40, Plano Diretor
   Sul" em Taquaralto (22 km) — e o pino certo foi descartado.
2. A zona de taxa fixa (Taquaralto R$ 40, keywords "Aureny", "Bertaville"...)
   casava palavra do TEXTO digitado junto com o reverso do ponto. Com pino, o
   texto não pode escolher zona: quem escreve "perto do Aureny" no Plano
   Diretor pagaria R$ 40.

Pino antigo com endereço novo não é problema do servidor: no checkout,
digitar rua/bairro apaga o pino (useCheckoutForm.handleChange) e o mapa só
confirma o que o cliente vê. Endereço salvo viaja com o pino dele.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.unified_delivery_service import UnifiedDeliveryService

User = get_user_model()

PINO_DO_EMMANUEL = (-10.2102562, -48.335673)
TAQUARALTO = (-10.3266768, -48.3260618)
ENDERECO_DO_EMMANUEL = {
    'street': 'Acsu So 40, Conjunto 2, Lote 2', 'number': '00',
    'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77015558',
    'lat': PINO_DO_EMMANUEL[0], 'lng': PINO_DO_EMMANUEL[1],
    'coordinate_source': 'customer_selected_pin', 'coordinates_confirmed': True,
}
ZONAS_DA_CE = [
    {'fee': 25, 'name': 'Residencial Polinésia', 'keywords': ['polinesia']},
    {'fee': 40, 'name': 'Taquaralto', 'keywords': ['Bertaville', 'Aureny I', 'Aureny', 'Morada do Sol']},
]
REVERSO_PLANO_DIRETOR = {
    'formatted_address': 'Q. 401 Sul Avenida LO 11, 3-179 - Plano Diretor Sul, Palmas - TO, 77015-558, Brasil',
    'street': 'Quadra 401 Sul Avenida LO 11', 'neighborhood': 'Plano Diretor Sul',
    'city': 'Palmas', 'state': 'TO',
}
REVERSO_AURENY = {
    'formatted_address': 'Av. Siqueira Campos, 201 - Jardim Aureny III (Taquaralto), Palmas - TO',
    'street': 'Avenida Siqueira Campos', 'neighborhood': 'Jardim Aureny III (Taquaralto)',
    'city': 'Palmas', 'state': 'TO',
}


class CotacaoDoCheckoutTests(TestCase):
    """`calculate_delivery_fee_for_payload`: com pino, só o pino."""

    def _cotar(self, payload):
        with patch('apps.stores.services.geo.service.GeoService.geocode',
                   return_value={'lat': TAQUARALTO[0], 'lng': TAQUARALTO[1],
                                 'neighborhood': 'Plano Diretor Sul', 'location_type': 'PREMISE'}) as geocode, \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value={'success': True, 'fee': 10.5, 'distance_km': 6.75}) as calc:
            CheckoutService.calculate_delivery_fee_for_payload(MagicMock(), payload)
        return calc.call_args.kwargs, geocode

    def test_pino_do_emmanuel_vale_mesmo_com_o_google_errando_o_texto(self):
        kw, geocode = self._cotar({'method': 'delivery', 'address': ENDERECO_DO_EMMANUEL})
        self.assertEqual((kw['lat'], kw['lng']), PINO_DO_EMMANUEL)
        geocode.assert_not_called()  # sem trava: o texto nem é consultado

    def test_pino_no_payload_tambem_vale(self):
        endereco = {k: v for k, v in ENDERECO_DO_EMMANUEL.items() if k not in ('lat', 'lng')}
        kw, _ = self._cotar({'method': 'delivery', 'lat': PINO_DO_EMMANUEL[0],
                             'lng': PINO_DO_EMMANUEL[1], 'address': endereco})
        self.assertEqual((kw['lat'], kw['lng']), PINO_DO_EMMANUEL)

    def test_pino_vindo_do_gps_ou_endereco_salvo_tambem_vale(self):
        # Não há mais "pino de segunda classe": o que está no mapa é a entrega.
        endereco = dict(ENDERECO_DO_EMMANUEL, coordinate_source=None, coordinates_confirmed=False)
        kw, _ = self._cotar({'method': 'delivery', 'address': endereco})
        self.assertEqual((kw['lat'], kw['lng']), PINO_DO_EMMANUEL)

    def test_pino_em_texto_vira_numero(self):
        endereco = dict(ENDERECO_DO_EMMANUEL, lat='-10.2102562', lng='-48.335673')
        kw, _ = self._cotar({'method': 'delivery', 'address': endereco})
        self.assertEqual((kw['lat'], kw['lng']), PINO_DO_EMMANUEL)

    def test_sem_pino_usa_o_endereco_escrito(self):
        endereco = {k: v for k, v in ENDERECO_DO_EMMANUEL.items() if k not in ('lat', 'lng')}
        kw, _ = self._cotar({'method': 'delivery', 'address': endereco})
        self.assertIsNone(kw['lat'])
        self.assertIn('Acsu So 40', kw['address_text'])

    def test_pino_invalido_conta_como_sem_pino(self):
        for lat, lng in (('abc', '-48.3'), (0, 0), (None, -48.3), (91, -48.3), (-10.2, 200),
                         (float('nan'), -48.3)):
            with self.subTest(lat=lat, lng=lng):
                endereco = dict(ENDERECO_DO_EMMANUEL, lat=lat, lng=lng)
                kw, _ = self._cotar({'method': 'delivery', 'address': endereco})
                self.assertIsNone(kw['lat'])
                self.assertIsNotNone(kw['address_text'])


class ZonaFixaPeloPinoTests(TestCase):
    """A zona de taxa fixa sai de ONDE O PINO ESTÁ, não do que foi digitado."""

    def setUp(self):
        dono = User.objects.create_user(username='dono-pino-manda', password='x')
        self.loja = Store.objects.create(
            name='Cê', slug='ce-pino-manda', owner=dono, status='active',
            latitude=Decimal('-10.1850'), longitude=Decimal('-48.3300'),
            metadata={'fixed_price_zones': ZONAS_DA_CE, 'delivery_max_km': 16},
        )

    def _cotar(self, reverso, address_text, lat=None, lng=None, achado=None):
        with patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value=reverso), \
             patch('apps.stores.services.geo.service.GeoService.localizar', return_value=achado), \
             patch.object(UnifiedDeliveryService, '_calculate_distance_and_duration',
                          return_value={'success': True, 'distance_km': 6.75, 'duration_minutes': 15}):
            return UnifiedDeliveryService.calculate_delivery_fee(
                store=self.loja, delivery_method='delivery', address_text=address_text, lat=lat, lng=lng,
            )

    def test_palavra_da_zona_no_texto_nao_puxa_o_pino_do_plano_diretor(self):
        r = self._cotar(REVERSO_PLANO_DIRETOR, 'Rua Aureny, 12, Plano Diretor Sul, Palmas, TO',
                        lat=PINO_DO_EMMANUEL[0], lng=PINO_DO_EMMANUEL[1])
        self.assertTrue(r['success'])
        self.assertNotEqual(r['zone_name'], 'Taquaralto')
        self.assertEqual(r['coordinate_source'], 'pin')

    def test_pino_no_aureny_cai_na_zona_taquaralto(self):
        r = self._cotar(REVERSO_AURENY, 'Acsu So 40, Plano Diretor Sul, Palmas, TO',
                        lat=TAQUARALTO[0], lng=TAQUARALTO[1])
        self.assertEqual(r['zone_name'], 'Taquaralto')
        self.assertEqual(r['fee'], 40.0)

    def test_sem_pino_o_texto_ainda_escolhe_a_zona(self):
        # Sem pino, o texto É o endereço: condomínio digitado continua valendo.
        r = self._cotar({'formatted_address': 'Palmas - TO', 'city': 'Palmas'},
                        'Residencial Polinésia, casa 4, Palmas, TO',
                        achado={'lat': -10.25, 'lng': -48.31, 'formatted_address': 'Palmas'})
        self.assertEqual(r['zone_name'], 'Residencial Polinésia')
        self.assertEqual(r['coordinate_source'], 'endereco_escrito')


class RegiaoDoPedidoTests(TestCase):
    """`regiao_do_pedido` (regras da região no checkout) também só olha o pino."""

    def test_texto_com_palavra_da_zona_nao_muda_a_regiao_do_pino(self):
        from apps.stores.services import regioes_de_entrega as regioes
        loja = MagicMock(metadata={'fixed_price_zones': ZONAS_DA_CE})
        with patch('apps.stores.services.geo.geo_service._match_fixed_price_zone',
                   return_value=None) as casar:
            regioes.regiao_do_pedido(loja, {
                'method': 'delivery',
                'address': dict(ENDERECO_DO_EMMANUEL, street='Rua Aureny'),
            })
        self.assertEqual(casar.call_args.kwargs.get('address_text', ''), '')
