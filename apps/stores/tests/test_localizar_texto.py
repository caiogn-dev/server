"""05/10 — PDV: "Secretaria da Segurança Pública" deu R$ 15 em vez de R$ 11.

Sem pino, o frete sai do texto. O Google não acha "Secretaria da ..." como
endereço e devolve o centro genérico de Palmas (-10.249091, -48.3242858,
granularidade OTHER), a 7 km da loja → 9,3 km de rota. Mesma causa da Ana
(Secretaria da Cidadania e Justiça). Como estabelecimento, o Google acha os
dois lugares certos, na Praça dos Girassóis.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.stores.services.geo.service import GeoService

GENERICO = {'lat': -10.249091, 'lng': -48.3242858, 'location_type': 'OTHER',
            'formatted_address': 'Palmas - TO, Brasil'}
SSP = {'name': 'Secretaria da Segurança Pública', 'lat': -10.1876554, 'lng': -48.3362503,
       'formatted_address': 'Praça dos Girassóis, S/n - Marco Central, Palmas - TO'}
RUA = {'lat': -10.2258355, 'lng': -48.319446, 'location_type': 'RANGE_INTERPOLATED',
       'formatted_address': 'Alameda 5, 12 - 706 Sul, Palmas - TO'}


class LocalizarTests(TestCase):
    def test_texto_que_o_geocode_nao_acha_vira_estabelecimento(self):
        with patch.object(GeoService, 'geocode', return_value=GENERICO), \
                patch.object(GeoService().provider.__class__, 'search_places', return_value=[SSP]) as places:
            achado = GeoService().localizar('Secretaria da Segurança Pública')
        self.assertEqual((achado['lat'], achado['lng']), (SSP['lat'], SSP['lng']))
        self.assertIn('Palmas', places.call_args.args[0])

    def test_endereco_preciso_nao_procura_estabelecimento(self):
        with patch.object(GeoService, 'geocode', return_value=RUA), \
                patch.object(GeoService().provider.__class__, 'search_places') as places:
            achado = GeoService().localizar('706 Sul Alameda 5, 12')
        self.assertEqual((achado['lat'], achado['lng']), (RUA['lat'], RUA['lng']))
        places.assert_not_called()

    def test_nada_preciso_devolve_none_em_vez_do_centro_generico(self):
        with patch.object(GeoService, 'geocode', return_value=GENERICO), \
                patch.object(GeoService().provider.__class__, 'search_places', return_value=[]):
            self.assertIsNone(GeoService().localizar('lugar que não existe'))


class FreteDoTextoTests(TestCase):
    """O cálculo por texto (PDV, bot, checkout sem pino) usa `localizar`."""

    def test_unified_usa_o_estabelecimento(self):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        with patch.object(GeoService, 'localizar', return_value={**SSP, 'location_type': 'PLACE'}) as loc:
            coords = UnifiedDeliveryService._resolve_coordinates(store=None, address_text='Secretaria da Segurança Pública')
        loc.assert_called_once()
        self.assertEqual((coords['lat'], coords['lng']), (SSP['lat'], SSP['lng']))

    def test_unified_sem_lugar_preciso_falha_em_vez_de_cobrar_errado(self):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        with patch.object(GeoService, 'localizar', return_value=None):
            coords = UnifiedDeliveryService._resolve_coordinates(store=None, address_text='xyz')
        self.assertFalse(coords['success'])


class EndpointDoPdvTests(TestCase):
    """POST /stores/<slug>/delivery-fee/ só com o texto — é o que o Novo
    pedido manda quando não há pino."""

    def setUp(self):
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from apps.stores.models import Store
        dono = get_user_model().objects.create_user(username='ow-loc', password='x')
        self.store = Store.objects.create(
            name='Loja Loc', slug='loja-loc', owner=dono, status='active',
            latitude=Decimal('-10.1852683'), longitude=Decimal('-48.3036368'),
        )

    def _post(self, address):
        from rest_framework.test import APIClient
        return APIClient().post(f'/api/v1/stores/{self.store.slug}/delivery-fee/', {'address': address}, format='json')

    def test_usa_o_ponto_do_estabelecimento(self):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        with patch.object(GeoService, 'localizar', return_value={**SSP, 'location_type': 'PLACE'}), \
                patch.object(UnifiedDeliveryService, 'calculate_delivery_fee',
                             return_value={'success': True, 'fee': 10.5, 'distance_km': 4.5}) as calc:
            resp = self._post('Secretaria da Segurança Pública')
        self.assertEqual(resp.status_code, 200, resp.content)
        kw = calc.call_args.kwargs
        self.assertEqual((kw['lat'], kw['lng']), (SSP['lat'], SSP['lng']))

    def test_lugar_nao_achado_pede_o_mapa_em_vez_de_cobrar_do_centro(self):
        with patch.object(GeoService, 'localizar', return_value=None):
            resp = self._post('lugar que não existe')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('mapa', resp.json()['error'])
