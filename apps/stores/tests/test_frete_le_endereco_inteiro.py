"""O cálculo do frete lê o endereço no formato em que os caminhos o mandam.

Até 29/05 `DeliveryQuoteService.calculate_for_payload` pegava a coordenada de
dentro do endereço (`address.lat/lng`, `latitude/longitude`) e o texto incluía
`raw_address`. O 03967153 trocou o miolo por `UnifiedDeliveryService` e passou a
ler só `payload['lat']` no topo e só street/number/bairro/cidade/UF.

Quem sentia: o bot do WhatsApp (`order_service._build_delivery_address`) grava
lat/lng e `raw_address` DENTRO do endereço. Sem taxa pronta, o checkout
ignorava o pin e geocodificava "Palmas, TO" — que `localizar` recusa por ser o
centro genérico — e o pedido caía em "Não achei esse endereço no mapa".
"""
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.stores.models import Store
from apps.stores.services.checkout_service import CheckoutService

pytestmark = pytest.mark.django_db

ROTA_3KM = {'distance_meters': 3000, 'duration_seconds': 600}


@pytest.fixture
def loja(django_user_model):
    dono = django_user_model.objects.create_user(username='dono-endereco', password='x')
    return Store.objects.create(
        owner=dono, name='Loja', slug='loja-endereco',
        default_delivery_fee=Decimal('8.00'),
        latitude=Decimal('-10.1852683'), longitude=Decimal('-48.3036368'),
        city='Palmas', state='TO',
    )


@patch('apps.stores.services.geo.service.GeoService.geocode', return_value=None)
@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_coordenada_dentro_do_endereco_e_usada(_rota, _geo, loja):
    r = CheckoutService.calculate_delivery_fee_for_payload(loja, {
        'method': 'delivery',
        'address': {'raw_address': 'Quadra 104 Norte, 10', 'lat': -10.2, 'lng': -48.33,
                    'city': 'Palmas', 'state': 'TO'},
    })
    assert r['fee'] == 8.0, r
    assert _rota.call_args.args[1] == pytest.approx((-10.2, -48.33))


@patch('apps.stores.services.geo.service.GeoService.localizar')
@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_raw_address_entra_no_texto_geocodificado(_rota, localizar, loja):
    localizar.return_value = {'lat': -10.2, 'lng': -48.33, 'formatted_address': 'Q 104 N'}
    r = CheckoutService.calculate_delivery_fee_for_payload(loja, {
        'method': 'delivery',
        'address': {'raw_address': 'Quadra 104 Norte, 10', 'city': 'Palmas', 'state': 'TO'},
    })
    assert r['fee'] == 8.0, r
    assert 'Quadra 104 Norte' in localizar.call_args.args[0]


@patch('apps.stores.services.geo.service.GeoService.localizar')
@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_rua_estruturada_continua_vencendo(_rota, localizar, loja):
    localizar.return_value = {'lat': -10.2, 'lng': -48.33}
    CheckoutService.calculate_delivery_fee_for_payload(loja, {
        'method': 'delivery',
        'address': {'street': 'Rua A', 'number': '5', 'raw_address': 'texto velho',
                    'city': 'Palmas', 'state': 'TO'},
    })
    texto = localizar.call_args.args[0]
    assert texto.startswith('Rua A, 5')
    assert 'texto velho' not in texto
