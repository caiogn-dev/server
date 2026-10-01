"""Busca de endereço do checkout sugeria LOJA, não endereço (01/10).

"Quadra 104 Norte Palmas" voltava Câmara Municipal, clínica, ótica… porque o
autocomplete do Google ia sem `types`. Agora pede endereços (`geocode`) e só
cai na busca aberta quando não há nenhum — quem digita "Shopping X" ainda acha.
"""
from unittest.mock import MagicMock, patch

from apps.stores.services.geo.google_provider import GoogleMapsProvider


def _resposta(predictions, status='OK'):
    r = MagicMock()
    r.json.return_value = {'status': status, 'predictions': predictions}
    r.raise_for_status.return_value = None
    return r


PRED = [{'description': 'Quadra 104 Norte, Palmas - TO', 'place_id': 'p1',
         'structured_formatting': {'main_text': 'Quadra 104 Norte', 'secondary_text': 'Palmas - TO'}}]


def _provider():
    p = GoogleMapsProvider.__new__(GoogleMapsProvider)
    p.api_key = 'k'
    p.geocode_place_id = lambda pid: {'lat': -10.18, 'lng': -48.33, 'address_components': {}}
    return p


def test_pede_enderecos_ao_google():
    with patch('apps.stores.services.geo.google_provider.requests.get', return_value=_resposta(PRED)) as get:
        out = _provider().autosuggest('Quadra 104 Norte Palmas')
    assert get.call_args.kwargs['params']['types'] == 'geocode'
    assert out[0]['main_text'] == 'Quadra 104 Norte'


def test_sem_endereco_cai_na_busca_aberta():
    respostas = [_resposta([], status='ZERO_RESULTS'), _resposta(PRED)]
    with patch('apps.stores.services.geo.google_provider.requests.get', side_effect=respostas) as get:
        out = _provider().autosuggest('Capim Dourado Shopping')
    assert get.call_count == 2
    assert 'types' not in get.call_args_list[1].kwargs['params']
    assert len(out) == 1
