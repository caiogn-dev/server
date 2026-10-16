"""A coordenada precisa concordar com o endereço escrito.

Dois pedidos reais em 20/08 saíram com o texto CERTO e o pin a quilômetros:

    Yasmine  "Secretaria da Cidadania e Justiça"  →  pin 4,45 km longe
    Barbara  "Av JK 110 Sul, Clínica DVI"         →  pin 5,16 km longe (706 Sul)

O entregador segue o pin, não o texto. E o frete é calculado pelo pin, então o
cliente ainda paga a distância errada.

Como a coordenada velha entra: a pessoa mexe no mapa, não consegue finalizar,
digita o endereço na mão — e a coordenada de antes fica. O front tem trava para
isso (`CAMPOS_QUE_MOVEM_O_PONTO`), mas ela só cobre o `onChange` dos inputs;
endereço salvo e outros caminhos passam por fora. Pior: uma vez gravado, o
endereço salvo repete o erro em TODO pedido seguinte — a Barbara errou igual em
14/08 e em 20/08, com a mesma coordenada.

Já se tentou consertar isso antes rotulando a origem da coordenada
(`coordinate_source`). O rótulo ajuda a diagnosticar e não impede nada: os dois
pedidos de hoje vieram rotulados e saíram errados assim mesmo.

Por isso a checagem vive no BACKEND: é o único ponto por onde todos os
caminhos passam. Se o pin discorda do texto, o texto ganha — ele é o que a
pessoa escreveu e o que ela lê na confirmação.
"""
import math

#: Distância a partir da qual pin e texto são considerados incompatíveis.
#: Palmas tem quadras largas; 1,5 km é folgado o bastante para não brigar com
#: imprecisão de geocodificação e apertado o bastante para pegar os dois casos
#: reais (4,45 km e 5,16 km).
TOLERANCIA_KM = 1.5


def distancia_km(lat1, lng1, lat2, lng2) -> float:
    """Haversine. Sem dependência externa — é uma conta de trigonometria."""
    R = 6371.0
    rad = math.radians
    dlat = rad(lat2 - lat1)
    dlng = rad(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def ponto_confere_com_texto(lat, lng, lat_do_texto, lng_do_texto,
                            tolerancia_km: float = TOLERANCIA_KM) -> bool:
    """True quando dá para confiar na coordenada informada.

    Sem uma das duas pontas não há como comparar — e nesse caso NÃO se descarta
    o pin: derrubar coordenada por falta de prova quebraria quem está certo.
    """
    if None in (lat, lng, lat_do_texto, lng_do_texto):
        return True
    return distancia_km(float(lat), float(lng),
                        float(lat_do_texto), float(lng_do_texto)) <= tolerancia_km


#: Granularidades do Google que NÃO localizam o endereço — são o "não achei,
#: toma o centro de Palmas" (-10.249091, -48.3242858). Em 05/10 a Ana pagou
#: R$ 15,29 em vez de R$ 10,50: o texto "Praça dos Girassóis, S/n" voltou como
#: OTHER/APPROXIMATE, ficou a 7 km do pin certo, e o pin foi descartado.
GRANULARIDADES_IMPRECISAS = frozenset({'OTHER', 'APPROXIMATE', 'GRANULARITY_UNSPECIFIED'})


def geocode_e_preciso(geo) -> bool:
    """True quando o geocode do texto achou um lugar de verdade.

    Só um geocode preciso pode derrubar o pin: comparar o pin com o centro
    genérico da cidade descarta justamente quem marcou certo.
    """
    if not geo or geo.get('lat') is None or geo.get('lng') is None:
        return False
    return (geo.get('location_type') or '').upper() not in GRANULARIDADES_IMPRECISAS


def _rua_normalizada(texto) -> str:
    import re
    import unicodedata
    plano = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    plano = re.sub(r'[^a-z0-9 ]+', ' ', plano)
    plano = re.sub(r'\bav\b', 'avenida', plano)
    return ' '.join(plano.split())


def pino_esta_no_endereco(reverso, endereco) -> bool:
    """True quando o pin cai na MESMA rua e número que o cliente tem escritos.

    16/10, Ana Loyse: o texto do pedido era o próprio reverso do pin na UFT
    ("Av. NS 15, 109"), mas o Google geocodifica esse texto como "Av. NS-03,
    15-109", a 2 km — e o pin certo era descartado. Quando o reverso do pin
    confirma rua E número, o pin é a prova; o geocode do texto é que errou.
    Rua sozinha não basta: avenida comprida tem quilômetros.
    """
    if not reverso or not isinstance(endereco, dict):
        return False
    rua_pin, rua_txt = _rua_normalizada(reverso.get('street')), _rua_normalizada(endereco.get('street'))
    num_pin = str(reverso.get('number') or '').strip().lstrip('0')
    num_txt = str(endereco.get('number') or '').strip().lstrip('0')
    return bool(rua_pin and num_pin) and rua_pin == rua_txt and num_pin == num_txt
