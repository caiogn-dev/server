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
