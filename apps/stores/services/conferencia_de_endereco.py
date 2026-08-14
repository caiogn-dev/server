"""Confere se o pin do pedido concorda com o endereço que o cliente escreveu.

Nasceu do pedido CE-2608140823 (Cê Saladas, 14/ago). A cliente escreveu
"Av jk 110 sul Clínica DVI" e o pin caiu na 706 Sul — 5,15 km de distância. O
link do Maps é montado das COORDENADAS, então o entregador foi para a 706. E o
frete sai do pin: ela pagou R$ 11,00 onde da outra vez pagou R$ 7,00.

O pedido veio marcado `coordinate_source: customer_selected_pin` com
`coordinates_confirmed: true`, e o sistema tratava isso como verdade absoluta.
Ninguém comparava o pin com o texto.

Três decisões de projeto:

- **Não bloqueia venda.** Recusar pedido por suspeita de endereço custa mais
  que a entrega errada. Isto só registra a contradição para a loja ver antes de
  o entregador sair.
- **Cala quando não sabe.** Sem pin, sem quadra no texto, geocoder fora do ar:
  devolve None. Alarme que toca sempre é alarme desligado.
- **Compara quadra, não distância.** Distância exige geocodificar o texto — mais
  uma chamada paga por pedido. A quadra já está escrita nos dois lados, e em
  Palmas ela é o que separa dois pontos a 5 km um do outro.
"""
import logging
import re

logger = logging.getLogger(__name__)

#: "110 sul", "Q. 706 Sul", "quadra 110sul", "110 NORTE". O que mais aparece nos
#: endereços de Palmas — e é justamente o token que distingue os dois pontos do
#: caso real.
_QUADRA = re.compile(r'\b(\d{3,4})\s*(sul|norte)\b', re.I)

_CHAVES_DE_TEXTO = ('street', 'raw_address', 'address', 'label', 'formatted_address')


def _quadra(texto) -> str:
    """Devolve "110 sul" normalizado, ou '' quando não há quadra no texto."""
    achado = _QUADRA.search(str(texto or ''))
    if not achado:
        return ''
    return f'{achado.group(1)} {achado.group(2).lower()}'


def _texto_do_pedido(endereco: dict) -> str:
    partes = [str(endereco.get(c) or '') for c in _CHAVES_DE_TEXTO]
    return ' '.join(p for p in partes if p)


def conferir(endereco, *, reverse_geocode=None):
    """Devolve a divergência, ou None quando não há o que apontar.

    `reverse_geocode(lat, lng)` é injetável para os testes não dependerem da
    API do Google. Em produção usa o GeoService, que já tem cache.
    """
    if not isinstance(endereco, dict):
        return None

    lat, lng = endereco.get('lat'), endereco.get('lng')
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None

    digitada = _quadra(_texto_do_pedido(endereco))
    if not digitada:
        # Endereço de rua comum — a maior parte do Brasil. Nada a comparar.
        return None

    if reverse_geocode is None:
        reverse_geocode = _reverse_do_geoservice

    try:
        resposta = reverse_geocode(float(lat), float(lng))
    except Exception as exc:
        # Geocoder fora do ar não pode virar alarme nem derrubar o pedido.
        logger.info('[conferencia] reverse falhou (%s) — sem opinião', exc)
        return None

    if not resposta:
        return None

    do_pin = _quadra(
        resposta.get('formatted_address') if isinstance(resposta, dict) else resposta
    )
    if not do_pin or do_pin == digitada:
        return None

    return {
        'digitado': digitada,
        'pin': do_pin,
        'lat': float(lat),
        'lng': float(lng),
        'aviso': (
            f'O cliente escreveu "{digitada}" mas o pin do mapa cai em '
            f'"{do_pin}". Confirme antes de sair para a entrega — o frete foi '
            f'calculado pelo pin.'
        ),
    }


def _reverse_do_geoservice(lat, lng):
    from apps.stores.services.geo.service import GeoService

    return GeoService().reverse_geocode(lat, lng)
