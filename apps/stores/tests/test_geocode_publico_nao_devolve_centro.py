"""O checkout da loja posiciona o pino pelo texto via /maps/geocode/.

Com `geocode()` cru, "Colégio Marista" virava o centro genérico de Palmas
(-10.249091) e o pino caía a 9 km do lugar (Nair, 20/10). Agora o endpoint
usa `localizar()`: o lugar, ou 404 — que o front já trata como "não achei".
"""
from unittest.mock import Mock, patch

from django.urls import reverse
from rest_framework.test import APIClient

from apps.stores.services.geo import geo_service

MARISTA = {'lat': -10.1913182, 'lng': -48.3123376, 'location_type': 'PLACE',
           'formatted_address': 'Q. 110 Sul Alameda 23 - 110 Sul, Palmas - TO'}


def _get(localizar):
    with patch.object(geo_service, 'localizar', Mock(return_value=localizar)), \
         patch.object(geo_service, 'geocode', Mock(return_value={'lat': -10.249091, 'lng': -48.3242858})):
        return APIClient().get(reverse('maps-geocode'), {'address': 'Colégio Marista'})


def test_devolve_o_lugar(db):
    resposta = _get(MARISTA)
    assert resposta.status_code == 200
    assert resposta.json()['lat'] == MARISTA['lat']


def test_sem_ponto_confiavel_e_404_nunca_o_centro(db):
    assert _get(None).status_code == 404
