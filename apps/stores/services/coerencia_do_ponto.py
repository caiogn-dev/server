"""Régua de distância e precisão de geocode.

ATÉ 19/11/2026 este módulo era a "trava de coerência": geocodificava o texto
do endereço e, se o pino ficasse longe, jogava o pino fora. Foi removida por
decisão do dono depois do Emmanuel (CE-2611190382): o Google pôs "ACSU SO 40,
Plano Diretor Sul" em Taquaralto, a trava descartou o pino CERTO que ele marcou
e o frete saiu R$ 40 por 6,75 km.

Regra de hoje: O PINO MARCADO NO MAPA É O ENDEREÇO DE ENTREGA. O texto só
calcula quando não há pino. Pino antigo com endereço novo se resolve no
checkout (digitar rua/bairro apaga o pino), não adivinhando no servidor.

Ficou o que outros usam:
- `distancia_km` / `TOLERANCIA_KM`: o aviso pós-pedido à loja
  (`conferencia_de_endereco`) — "o cliente escreveu X e o pino cai em Y,
  confira". Avisa, não muda o frete.
- `geocode_e_preciso`: o geocode recusa centro genérico de cidade.
"""
import math

#: Distância a partir da qual o aviso pós-pedido diz que texto e pino divergem.
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


#: Granularidade do Google que não é endereço: o "centro de Palmas"
#: (-10.249091, -48.3242858) volta como OTHER/APPROXIMATE.
GRANULARIDADES_IMPRECISAS = frozenset({'OTHER', 'APPROXIMATE', 'GRANULARITY_UNSPECIFIED'})


def geocode_e_preciso(geo) -> bool:
    """True quando o geocode do texto achou um lugar de verdade, não o centro da cidade."""
    if not geo or geo.get('lat') is None or geo.get('lng') is None:
        return False
    return (geo.get('location_type') or '').upper() not in GRANULARIDADES_IMPRECISAS
