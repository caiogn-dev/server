"""Endereço não pode ficar salvo como link do mapa nem como par de números.

O pin resolve a ENTREGA — o entregador segue a coordenada. Mas quem lê o
endereço depois não recebe entrega nenhuma: a comanda impressa, a etiqueta, o
relatório por bairro, a lista de endereços salvos do cliente e o próximo pedido
dele recebem "https://maps.app.goo.gl/i1Vcfc5fDj45Ja9U7". Foi o que aconteceu
no CE-2609103109 (Cê Saladas, 10/set, lançado pelo PDV).

Este módulo roda na ENTRADA do pedido, ao lado de `endereco_estruturado`, e
segue as mesmas duas regras:

1. **Nunca apagar.** O link vai para `maps_url` e o texto original para
   `raw_address_original`. Se a geocodificação falhar, o endereço volta como
   estava — link feio é melhor que endereço perdido.
2. **O que a pessoa escreveu vence.** Só preenche campo VAZIO.

E uma terceira, de custo: texto escrito por gente não gasta chamada de rede.
Só um endereço que é SÓ ponto no mapa aciona a geocodificação reversa.
"""
import logging
import re
from typing import Optional, Tuple
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_NUM = r'-?\d{1,3}\.\d{3,}'
_PAR_DE_COORDENADAS = re.compile(rf'({_NUM})\s*[,;]\s*({_NUM})')
# No link longo do Maps, `@lat,lng` é o CENTRO da tela e `!3d<lat>!4d<lng>` é o
# PIN. No link do CE-2609103109 os dois diferem 280 m — o centro entregaria na
# quadra errada. Quando o pin existe, é ele que vale.
_PIN_DO_MAPS = re.compile(rf'!3d({_NUM})!4d({_NUM})')
_SO_O_PAR = re.compile(rf'^\s*{_NUM}\s*[,;]\s*{_NUM}\s*$')
_URL = re.compile(r'^\s*https?://\S+\s*$', re.I)
_ROTULO_DE_PIN = re.compile(r'^\s*localiza[çc][ãa]o\s+enviada\b', re.I)

# Campos que a geocodificação reversa pode preencher.
_CAMPOS = ('street', 'number', 'neighborhood', 'city', 'state', 'zip_code')


def e_so_um_ponto_no_mapa(texto: str) -> bool:
    """O texto é só um link/coordenada, sem nome de lugar dentro?"""
    valor = (texto or '').strip()
    if not valor:
        return False
    return bool(_URL.match(valor) or _SO_O_PAR.match(valor) or _ROTULO_DE_PIN.match(valor))


def coordenadas_do_texto(texto: str) -> Optional[Tuple[float, float]]:
    """Lê lat/lng de um par cru, do rótulo do PDV ou de um link do Maps."""
    valor = unquote((texto or '').strip())
    achado = _PIN_DO_MAPS.search(valor) or _PAR_DE_COORDENADAS.search(valor)
    if not achado:
        return None
    try:
        return float(achado.group(1)), float(achado.group(2))
    except ValueError:
        return None


def _coords_do_link_curto(url: str) -> Optional[Tuple[float, float]]:
    """Segue o redirecionamento de um link curto (maps.app.goo.gl) até as coordenadas.

    Só o servidor consegue fazer isto: o navegador esbarra no CORS, e é por isso
    que o link curto chegava cru até o banco.
    """
    try:
        import requests
        resposta = requests.head(url, allow_redirects=True, timeout=6)
        return coordenadas_do_texto(resposta.url)
    except Exception as exc:  # rede é opcional: sem ela o endereço fica como está
        logger.info('nome_do_lugar: link curto não resolvido (%s): %s', url, exc)
        return None


def _reverse_geocode(lat: float, lng: float):
    from apps.stores.services.geo.service import GeoService
    return GeoService().reverse_geocode(lat, lng)


def _uf(bruto: dict) -> str:
    """Prefere a sigla — `state` da geocodificação vem "Tocantins"."""
    return (bruto.get('state_code') or bruto.get('state') or '').strip()


def nomear_se_for_so_um_ponto(endereco: dict) -> dict:
    """Dá nome ao lugar quando o endereço é só um link ou uma coordenada."""
    if not isinstance(endereco, dict) or not endereco:
        return endereco

    texto = str(endereco.get('street') or endereco.get('address') or '').strip()
    if not e_so_um_ponto_no_mapa(texto):
        return endereco

    lat, lng = endereco.get('lat'), endereco.get('lng')
    if lat is None or lng is None:
        do_texto = coordenadas_do_texto(texto)
        if do_texto is None and _URL.match(texto):
            do_texto = _coords_do_link_curto(texto)
        if do_texto is None:
            return endereco  # sem coordenada não há o que geocodificar
        lat, lng = do_texto

    try:
        achado = _reverse_geocode(float(lat), float(lng))
    except Exception as exc:
        logger.info('nome_do_lugar: geocodificação reversa falhou: %s', exc)
        return endereco

    if not achado or not (achado.get('street') or achado.get('city')):
        return endereco

    saida = dict(endereco)

    # Nunca apagar o que chegou.
    if _URL.match(texto) and not saida.get('maps_url'):
        saida['maps_url'] = texto
    if not saida.get('raw_address_original'):
        saida['raw_address_original'] = texto

    valores = {
        'street': (achado.get('street') or '').strip(),
        'number': (achado.get('number') or '').strip(),
        'neighborhood': (achado.get('neighborhood') or '').strip(),
        'city': (achado.get('city') or '').strip(),
        'state': _uf(achado),
        'zip_code': (achado.get('zip_code') or '').strip(),
    }
    # A rua é o campo que estava ocupado pelo link: essa, sim, é substituída.
    if valores['street']:
        saida['street'] = valores['street']
        saida.pop('address', None)
    for campo in _CAMPOS:
        if campo != 'street' and valores[campo] and not str(saida.get(campo) or '').strip():
            saida[campo] = valores[campo]

    saida.setdefault('lat', lat)
    saida.setdefault('lng', lng)
    saida['coordinate_source'] = saida.get('coordinate_source') or 'reverse_geocode'
    return saida
