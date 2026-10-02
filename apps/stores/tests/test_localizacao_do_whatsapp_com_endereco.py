"""Localização do WhatsApp chegava no painel só como coordenada (02/10).

O cliente manda o pino; o WhatsApp entrega só latitude/longitude. O painel
tentava dar nome ao ponto chamando /stores/maps/reverse-geocode/ — rota que não
existe (404, engolido) — e o pedido ficava "Localização enviada (-10.18, -48.32)".
Agora o próprio endpoint de localização devolve o endereço legível e os campos.
"""
from apps.stores.services.localizacao_do_whatsapp import endereco_da_localizacao

REVERSE_106N = {
    'street': 'Q. 106 Norte Alameda 10', 'number': '2', 'neighborhood': 'Plano Diretor Norte',
    'city': 'Palmas', 'state_code': 'TO', 'zip_code': '77006-080',
    'formatted_address': '2 - Q. 106 Norte Alameda 10, 2 - Plano Diretor Norte, Palmas - TO',
}


def test_pin_sem_endereco_ganha_endereco_legivel_e_campos():
    loc = {'latitude': -10.1809, 'longitude': -48.3216}
    r = endereco_da_localizacao(loc, reverse=lambda lat, lng: REVERSE_106N)
    assert r['address'] == 'Q. 106 Norte Alameda 10, 2 — Plano Diretor Norte, Palmas-TO'
    assert r['street'] == 'Q. 106 Norte Alameda 10'
    assert r['neighborhood'] == 'Plano Diretor Norte'
    assert r['city'] == 'Palmas' and r['state'] == 'TO'


def test_endereco_que_veio_do_whatsapp_e_mantido():
    loc = {'latitude': -10.18, 'longitude': -48.32, 'name': 'Capim Dourado Shopping', 'address': 'Q. 107 Norte, Av. NS 5'}
    r = endereco_da_localizacao(loc, reverse=lambda lat, lng: REVERSE_106N)
    assert r['address'] == 'Q. 107 Norte, Av. NS 5'
    assert r['name'] == 'Capim Dourado Shopping'


def test_geocoder_fora_do_ar_nao_quebra():
    def explode(lat, lng):
        raise RuntimeError('google fora')
    r = endereco_da_localizacao({'latitude': -10.18, 'longitude': -48.32}, reverse=explode)
    assert r['address'] == ''
    assert r['lat'] == -10.18
