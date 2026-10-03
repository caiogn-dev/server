"""Localização da PRÓPRIA loja no painel (03/10).

O dono não conseguia achar "Agrião Comida Saudável" no Google: a busca pede só
endereços (types=geocode) e cai na busca aberta apenas se não houver nenhum.
Para a localização da loja o alvo É o estabelecimento. E a tela só aceitava
latitude/longitude digitadas — a Agrião estava com as coordenadas da Cê.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.stores.models import Store
from apps.stores.services.geo.google_provider import GoogleMapsProvider


def _resposta(predictions, status='OK'):
    r = MagicMock()
    r.json.return_value = {'status': status, 'predictions': predictions}
    r.raise_for_status.return_value = None
    return r


PRED = [{'description': 'Agrião Comida Saudável - Plano Diretor Sul, Palmas - TO', 'place_id': 'p9',
         'structured_formatting': {'main_text': 'Agrião Comida Saudável', 'secondary_text': 'Palmas - TO'}}]


def _provider():
    p = GoogleMapsProvider.__new__(GoogleMapsProvider)
    p.api_key = 'k'
    p.geocode_place_id = lambda pid: {'lat': -10.2, 'lng': -48.33, 'address_components': {}}
    return p


def test_modo_estabelecimento_nao_filtra_por_endereco():
    with patch('apps.stores.services.geo.google_provider.requests.get', return_value=_resposta(PRED)) as get:
        out = _provider().autosuggest('Agrião Comida Saudável', tipos=None)
    assert 'types' not in get.call_args.kwargs['params']
    assert out[0]['main_text'] == 'Agrião Comida Saudável'


def test_padrao_continua_pedindo_endereco():
    with patch('apps.stores.services.geo.google_provider.requests.get', return_value=_resposta(PRED)) as get:
        _provider().autosuggest('Quadra 104 Norte')
    assert get.call_args.kwargs['params']['types'] == 'geocode'


class PontoDoLinkTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.dono = User.objects.create_user('dono_loc', 'dono@loc.com', 'x')
        self.loja = Store.objects.create(name='Agrião', slug='agriao-loc', owner=self.dono, status='active')
        self.url = f'/api/v1/stores/{self.loja.slug}/ponto-do-link/'

    def test_link_completo_do_maps_vira_coordenada(self):
        c = APIClient()
        c.force_authenticate(self.dono)
        link = 'https://www.google.com/maps/place/Agri%C3%A3o/@-10.2101,-48.3301,17z/data=!3d-10.2105!4d-48.3305'
        r = c.get(self.url, {'link': link})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertAlmostEqual(r.data['lat'], -10.2105, places=3)
        self.assertAlmostEqual(r.data['lng'], -48.3305, places=3)

    def test_link_que_nao_e_do_maps_e_recusado(self):
        c = APIClient()
        c.force_authenticate(self.dono)
        r = c.get(self.url, {'link': 'https://exemplo.com/x'})
        self.assertEqual(r.status_code, 400)

    def test_anonimo_nao_usa(self):
        r = APIClient().get(self.url, {'link': 'https://maps.app.goo.gl/abc'})
        self.assertIn(r.status_code, (401, 403))
