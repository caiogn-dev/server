"""A régua do frete não pode quebrar quando a loja não tem coordenada no campo.

`UnifiedDeliveryService._calculate_distance_and_duration` passava
`(store.latitude, store.longitude)` cru para `GeoService._get_route`, que faz
`round(lat, 4)` logo na entrada. Com a coluna vazia isso estourava
`type NoneType doesn't define __round__ method` (e `type str ...` quando a
coordenada chegava como texto); o `except` engolia, e o cliente via só
"Não consegui calcular a rota" — entrega recusada.

O resto do sistema já sabia onde mais procurar a loja: `GeoService._resolve_store_coords`
e `maps_views` caem para `metadata['store_latitude'/'store_longitude']`. A régua
única era a única que não caía.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.stores.models import Store
from apps.stores.services.unified_delivery_service import UnifiedDeliveryService

pytestmark = pytest.mark.django_db

ROTA_3KM = {'distance_meters': 3000, 'duration_seconds': 600}
CLIENTE = (-10.2000, -48.3300)


def _loja(django_user_model, slug, **campos):
    dono = django_user_model.objects.create_user(username=f'dono-{slug}', password='x')
    return Store.objects.create(
        owner=dono, name=slug, slug=slug,
        default_delivery_fee=Decimal('8.00'),
        **campos,
    )


@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_loja_com_coordenada_so_no_metadata_calcula_o_frete(_rota, django_user_model):
    loja = _loja(
        django_user_model, 'so-metadata',
        metadata={'store_latitude': '-10.1852683', 'store_longitude': '-48.3036368'},
    )
    assert loja.latitude is None

    r = UnifiedDeliveryService.calculate_delivery_fee(loja, lat=CLIENTE[0], lng=CLIENTE[1])

    assert r['success'] is True, r
    assert r['distance_km'] == 3.0
    origem = _rota.call_args.args[0]
    assert origem == pytest.approx((-10.1852683, -48.3036368))


@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_coordenada_em_texto_nao_quebra_o_round(_rota, django_user_model):
    loja = _loja(django_user_model, 'coord-texto')
    # Instância em memória com o valor como veio do formulário/serializer.
    loja.latitude, loja.longitude = '-10.1852683', '-48.3036368'

    r = UnifiedDeliveryService.calculate_delivery_fee(loja, lat=CLIENTE[0], lng=CLIENTE[1])

    assert r['success'] is True, r


@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
def test_loja_sem_coordenada_nenhuma_recusa_com_motivo_claro_e_sem_excecao(_rota, django_user_model, caplog):
    loja = _loja(django_user_model, 'sem-coord')

    with caplog.at_level('ERROR'):
        r = UnifiedDeliveryService.calculate_delivery_fee(loja, lat=CLIENTE[0], lng=CLIENTE[1])

    assert r['success'] is False
    assert r['fee'] is None
    assert 'localização da loja' in r['reason']
    assert not [x for x in caplog.records if 'Route calculation error' in x.getMessage()]
    _rota.assert_not_called()
