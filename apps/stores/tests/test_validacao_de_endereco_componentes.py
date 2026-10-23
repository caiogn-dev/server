"""Address Validation do Google: `componentType` é TEXTO, não lista.

22/10, Agrião: "Alameda 2, 407 Norte" voltava com street/bairro/cidade vazios.
O parser fazia `set("route")` = {'r','o','u','t','e'} e nenhum componente
casava — toda validação saía só com o formatted_address. O storefront lia
"sem rua" como "só achou o bairro" e mandava a cliente marcar no mapa.
"""
from apps.stores.services.geo.google_provider import GoogleMapsProvider


def _comp(tipo, texto, nivel='CONFIRMED'):
    return {'componentType': tipo, 'componentName': {'text': texto}, 'confirmationLevel': nivel}


# Resposta real (resumida) de 22/10 para "Alameda 2, 407 Norte, Palmas, TO".
PAYLOAD_407_NORTE = {
    'result': {
        'verdict': {'geocodeGranularity': 'SUB_PREMISE'},
        'geocode': {'location': {'latitude': -10.1592638, 'longitude': -48.3522231}, 'placeId': 'x'},
        'address': {
            'formattedAddress': 'Alameda, 2 - Plano Diretor Norte, Palmas - TO, 77001-572, Brasil',
            'addressComponents': [
                _comp('route', 'Alameda', 'UNCONFIRMED_BUT_PLAUSIBLE'),
                _comp('street_number', '2'),
                _comp('route', 'Quadra 407 Norte Alameda 1'),
                _comp('administrative_area_level_2', 'Palmas'),
                _comp('administrative_area_level_1', 'TO'),
                _comp('country', 'Brasil'),
                _comp('postal_code', '77001-572'),
                _comp('sublocality_level_1', 'Plano Diretor Norte'),
            ],
        },
    },
}


def _parse(payload):
    return GoogleMapsProvider(api_key='teste')._parse_validated_address(payload)


def test_componente_em_texto_preenche_rua_bairro_cidade():
    c = _parse(PAYLOAD_407_NORTE)['address_components']
    assert c['number'] == '2'
    assert c['neighborhood'] == 'Plano Diretor Norte'
    assert c['city'] == 'Palmas'
    assert c['state'] == 'TO'
    assert c['zip_code'] == '77001-572'


def test_rua_confirmada_vence_a_plausivel():
    """Duas `route`: "Alameda" (só plausível) e a confirmada com a quadra."""
    assert _parse(PAYLOAD_407_NORTE)['address_components']['street'] == 'Quadra 407 Norte Alameda 1'


def test_locality_continua_valendo_sobre_municipio():
    payload = {'result': {**PAYLOAD_407_NORTE['result'], 'address': {
        'formattedAddress': 'x',
        'addressComponents': [
            _comp('administrative_area_level_2', 'Município'),
            _comp('locality', 'Palmas'),
        ],
    }}}
    assert _parse(payload)['address_components']['city'] == 'Palmas'


def test_lista_de_tipos_tambem_funciona():
    payload = {'result': {**PAYLOAD_407_NORTE['result'], 'address': {
        'formattedAddress': 'x',
        'addressComponents': [{'componentType': ['route'], 'componentName': {'text': 'Rua A'}}],
    }}}
    assert _parse(payload)['address_components']['street'] == 'Rua A'
