"""O endereço do pedido, com cada campo recebendo o que é dele.

Alguns caminhos do checkout gravavam o endereço formatado inteiro dentro de
`street` — às vezes duas vezes:

    "Quadra 501 Sul Avenida NS 1, 9, Recepção da ortolife - Centro, Palmas, TO,
     9, Recepção da ortolife - Centro, Palmas, TO"

O painel aprendeu a limpar isso na EXIBIÇÃO, mas limpar na saída não conserta
quem lê o dado direto: etiqueta, roteirização, relatório por bairro e qualquer
integração continuam recebendo a sopa. A estrutura tem que acontecer na
ENTRADA.

DUAS REGRAS:

1. **Nunca apagar.** Se o texto não couber em nenhum campo conhecido, ele
   sobrevive em `raw_address_original`. Endereço é o que faz a entrega chegar;
   perder um pedaço é pior que guardar demais.
2. **O que o cliente digitou vence.** Só preenchemos campo VAZIO com o que foi
   extraído da rua suja. Quem escreveu "apto 302" não pode ser sobrescrito por
   um palpite do parser.
"""
import re

# A rua vem "suja" quando carrega o resto do endereço junto. O separador que os
# formatadores usam para colar o bairro é " - ", e cidade/UF vêm por vírgula.
_SEPARADOR_BAIRRO = ' - '
_UF = re.compile(r'^[A-Z]{2}$')
_SO_NUMERO = re.compile(r'^\d{1,6}[A-Za-z]?$')

_CAMPOS = ('street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code')


def _texto(v) -> str:
    return str(v).strip() if v is not None else ''


def _partes(valor: str):
    """Quebra por vírgula preservando a ordem, sem pedaços vazios."""
    return [p.strip() for p in valor.split(',') if p.strip()]


def _desdobrar_rua(rua: str) -> dict:
    """Separa uma rua suja nos campos que ela estava carregando.

    Devolve só o que conseguiu identificar com segurança. O que sobrar de
    ambíguo continua na rua — errar para o lado de manter é o certo aqui.
    """
    achados = {}
    if not rua:
        return achados

    # O " - " separa o endereço da localização: "Rua X, 45 - Centro, Palmas, TO"
    cabeca, _, cauda = rua.partition(_SEPARADOR_BAIRRO)
    if cauda:
        loc = _partes(cauda)
        # A UF é a última parte com duas letras maiúsculas.
        if loc and _UF.match(loc[-1]):
            achados['state'] = loc.pop()
        if loc:
            achados['neighborhood'] = loc[0]
        if len(loc) > 1:
            achados['city'] = loc[-1]

    # Na cabeça, um pedaço que é só número é o número da casa.
    cabeca_partes = _partes(cabeca)
    if len(cabeca_partes) > 1 and _SO_NUMERO.match(cabeca_partes[1]):
        achados['number'] = cabeca_partes[1]
        achados['street'] = cabeca_partes[0]
        # O que vier depois do número, antes do " - ", é complemento.
        resto = cabeca_partes[2:]
        if resto:
            achados['complement'] = ', '.join(resto)
    elif cauda:
        # Havia localização colada, mas a cabeça não tem número destacável:
        # ela inteira é a rua.
        achados['street'] = cabeca.strip()

    return achados


def _rua_esta_suja(rua: str, dados: dict) -> bool:
    """A rua carrega o resto do endereço?

    Uma vírgula sozinha não denuncia nada — "Rua 7, Lote 12" é nome de rua de
    verdade. O sinal é a rua conter o separador de bairro OU repetir a cidade
    que já veio em campo próprio.
    """
    if not rua:
        return False
    if _SEPARADOR_BAIRRO in rua:
        return True
    cidade = _texto(dados.get('city'))
    return bool(cidade) and cidade.lower() in rua.lower()


def estruturar_endereco(bruto) -> dict:
    """Devolve o endereço com cada informação no seu campo."""
    if not isinstance(bruto, dict) or not bruto:
        return {}

    saida = dict(bruto)
    rua = _texto(saida.get('street'))

    if _rua_esta_suja(rua, saida):
        # Guarda o original ANTES de mexer: estruturar não pode apagar.
        saida.setdefault('raw_address_original', rua)
        achados = _desdobrar_rua(rua)
        if achados.get('street'):
            saida['street'] = achados['street']
        for campo in ('number', 'complement', 'neighborhood', 'city', 'state'):
            # Só preenche o que está vazio: o que o cliente digitou vence.
            if achados.get(campo) and not _texto(saida.get(campo)):
                saida[campo] = achados[campo]

    # `raw_address` passa a ser derivado das partes, no formato que se lê em
    # voz alta. Sem isto ele guardaria a versão suja para sempre.
    linha1 = ', '.join(p for p in (_texto(saida.get('street')), _texto(saida.get('number'))) if p)
    local = ', '.join(
        p for p in (
            _texto(saida.get('neighborhood')),
            _texto(saida.get('city')),
            _texto(saida.get('state')),
        ) if p
    )
    montado = _SEPARADOR_BAIRRO.join(p for p in (linha1, local) if p)
    if montado:
        saida['raw_address'] = montado

    return saida


def estruturar_no_payload(delivery_payload):
    """Aplica a estrutura ao `address` de um payload de entrega, se houver."""
    if not isinstance(delivery_payload, dict):
        return delivery_payload
    endereco = delivery_payload.get('address')
    if not isinstance(endereco, dict) or not endereco:
        return delivery_payload
    novo = dict(delivery_payload)
    novo['address'] = estruturar_endereco(endereco)
    return novo
