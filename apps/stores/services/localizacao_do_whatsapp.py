"""Pino do WhatsApp → endereço legível para o painel (02/10).

O WhatsApp entrega a localização só com latitude/longitude (name/address vêm
vazios quase sempre). Sem isto o pedido lançado no painel ficava
"Localização enviada (-10.18, -48.32)": o painel tentava nomear o ponto numa
rota inexistente e o erro era engolido. O nome sai do GeoService (reverse,
com cache de 24 h), e o endereço que o próprio WhatsApp mandou tem prioridade.
"""
import logging

logger = logging.getLogger(__name__)


def _reverse_do_geoservice(lat, lng):
    from apps.stores.services.geo.service import GeoService

    return GeoService().reverse_geocode(lat, lng)


def endereco_da_localizacao(loc: dict, *, reverse=None) -> dict:
    lat, lng = float(loc['latitude']), float(loc['longitude'])
    saida = {
        'lat': lat, 'lng': lng,
        'name': loc.get('name') or '',
        'address': (loc.get('address') or '').strip(),
        'street': '', 'number': '', 'neighborhood': '', 'city': '', 'state': '', 'zip_code': '',
    }
    if saida['address']:
        return saida
    try:
        geo = (reverse or _reverse_do_geoservice)(lat, lng) or {}
    except Exception as exc:
        logger.info('[localizacao] reverse falhou (%s) — fica só a coordenada', exc)
        return saida
    uf = geo.get('state_code') or geo.get('state') or ''
    saida.update({
        'street': geo.get('street') or '',
        'number': geo.get('number') or '',
        'neighborhood': geo.get('neighborhood') or '',
        'city': geo.get('city') or '',
        'state': uf,
        'zip_code': geo.get('zip_code') or '',
    })
    inicio = ', '.join(p for p in (saida['street'], saida['number']) if p)
    com_bairro = ' — '.join(p for p in (inicio, saida['neighborhood']) if p)
    cidade = f"{saida['city']}-{uf}" if saida['city'] and uf else (saida['city'] or uf)
    saida['address'] = ', '.join(p for p in (com_bairro, cidade) if p)
    return saida
