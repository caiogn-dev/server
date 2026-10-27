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


def _quadras_de_palmas(texto) -> set:
    """Quadras escritas no formato de Palmas: '110 Sul', 'quadra 704 sul'.

    Só a forma por extenso (número + Sul/Norte). Sigla (ARSO 52 = 207 Sul)
    fica de fora de propósito: o dono pediu para não inventar tabela de
    conversão (02/10) — sem quadra reconhecível, este atalho não vale.
    """
    import re
    plano = _rua_normalizada(texto)
    return {(int(n), lado) for n, lado in re.findall(r'\b(\d{2,4}) (sul|norte)\b', plano)}


def pino_na_quadra_escrita(reverso, endereco) -> bool:
    """True quando o reverso do pin cai na MESMA quadra que o cliente escreveu.

    19/10, Bárbara (CE-2610195503): pin certo na 110 Sul, texto "Av jk quadra
    110 sul, Lote 21" — o Google devolveu o texto como PREMISE a ~4 km
    (ecoando o digitado), o pin foi descartado e a entrega saiu R$ 14,36 em
    vez de ~R$ 8. Rua e número do reverso ("Alameda 1, 56") nunca batem com
    "Av jk, Lote 21", mas a QUADRA bate: 110 Sul nos dois.

    Quadra vizinha não passa (Simone, 01/10: escreveu 704 Sul, pin na 702 Sul)
    e Sul não confunde com Norte.
    """
    if not reverso or not isinstance(endereco, dict):
        return False
    escrito = ' '.join(str(endereco.get(k) or '') for k in (
        'street', 'number', 'neighborhood', 'raw_address', 'label',
    ))
    quadras_escritas = _quadras_de_palmas(escrito)
    if not quadras_escritas:
        return False
    do_pino = _quadras_de_palmas(' '.join(str(reverso.get(k) or '') for k in (
        'street', 'neighborhood', 'formatted_address',
    )))
    return bool(do_pino) and do_pino <= quadras_escritas


def _bairros_do_resultado(nome) -> list:
    """'Jardim Aureny III (Taquaralto)' → ['jardim aureny iii', 'taquaralto']."""
    import re
    partes = re.split(r'[()]', str(nome or ''))
    return [p for p in (_rua_normalizada(x) for x in partes) if p]


def texto_achou_o_lugar_escrito(geo, endereco) -> bool:
    """O geocode do texto caiu no lugar que o cliente escreveu?

    27/10, Lais (CE-2610278982): "FIETO, 01, Parque" foi achado pelo NOME — o
    Google devolveu a outra FIETO, em Jardim Aureny III (Taquaralto), a 9,4 km
    do pin certo na Orla 14. Taquaralto não aparece em nada que ela escreveu:
    é um homônimo, e homônimo não é prova contra o pin.

    Já na 407 Norte (CE-2610157694, 15/10) o texto caiu em Plano Diretor Norte,
    o bairro escrito — ali o texto é a prova e o pin na 111 Sul tem que cair.
    Por isso não se mexe no tipo do resultado (PREMISE_PROXIMITY vale nos dois).

    Prova = o bairro do resultado aparece no que foi escrito, OU a quadra de
    Palmas escrita é a mesma do resultado. Sem bairro de um dos lados não há o
    que comparar e o texto continua valendo, como antes.
    """
    if not geo:
        return False
    if isinstance(endereco, dict):
        escrito = ' '.join(str(endereco.get(k) or '') for k in (
            'street', 'number', 'complement', 'neighborhood', 'raw_address', 'label',
        ))
        tem_bairro = bool(str(endereco.get('neighborhood') or '').strip())
    else:
        escrito = str(endereco or '')
        tem_bairro = bool(escrito.strip())

    quadras_escritas = _quadras_de_palmas(escrito)
    if quadras_escritas and quadras_escritas & _quadras_de_palmas(
        ' '.join(str(geo.get(k) or '') for k in ('street', 'neighborhood', 'formatted_address'))
    ):
        return True

    bairros = _bairros_do_resultado(geo.get('neighborhood'))
    if not bairros or not tem_bairro:
        return True
    escrito_normal = f' {_rua_normalizada(escrito)} '
    return any(f' {b} ' in escrito_normal for b in bairros)
