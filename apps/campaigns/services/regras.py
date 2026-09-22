"""O vocabulário de condições do público: campo · operador · valor.

Até 21/09 a audiência era um punhado de caixas fixas ("VIP", "inativos"). Quem
queria "pediu mais de 3 vezes E sumiu faz 30 dias E é do Plano Diretor" não
tinha como pedir — e é essa pergunta que vira campanha que vende.

DESENHO

  regra = {"grupos": [{"condicoes": [ {campo, operador, valor}, ... ]}, ...]}

  Dentro do grupo, as condições somam **E**. Entre grupos, somam **OU**. É a
  convenção de todo construtor de regra (Cloudflare, HubSpot, Salesforce), e
  vale a pena seguir porque quem já usou um entende o nosso sem explicação.

POR QUE O CATÁLOGO MORA AQUI

A tela LÊ os campos e operadores deste módulo em vez de manter a própria
lista. Duas listas viram dois vocabulários: a tela oferece "termina com" para
um campo numérico, o servidor recusa, e o lojista leva a culpa.

O QUE ESTE MÓDULO NÃO FAZ

Não vai ao banco. Recebe o perfil já montado por `segmentos.perfis_por_telefone`
e decide. Assim a mesma regra serve para a prévia (contar quantos são) e para o
disparo (decidir um a um), sem duas implementações.
"""
from __future__ import annotations

import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from django.utils import timezone

NUMERO = 'numero'
TEXTO = 'texto'
DATA = 'data'
LISTA = 'lista'

#: O catálogo. Cada campo diz o TIPO, e o tipo decide os operadores — é isso
#: que impede a tela de oferecer "maior que" para bairro.
CAMPOS = [
    {'campo': 'pedidos', 'rotulo': 'Pedidos feitos', 'tipo': NUMERO},
    {'campo': 'ticket_medio', 'rotulo': 'Ticket médio', 'tipo': NUMERO, 'formato': 'dinheiro'},
    {'campo': 'ultima_compra', 'rotulo': 'Última compra', 'tipo': DATA},
    {'campo': 'bairro', 'rotulo': 'Bairro', 'tipo': TEXTO},
    {'campo': 'produto', 'rotulo': 'Produto', 'tipo': LISTA, 'fonte': 'produtos'},
]

OPERADORES = {
    NUMERO: [
        {'operador': 'maior_que', 'rotulo': 'é maior que'},
        {'operador': 'menor_que', 'rotulo': 'é menor que'},
        {'operador': 'e_igual_a', 'rotulo': 'é igual a'},
        {'operador': 'entre', 'rotulo': 'está entre', 'valores': 2},
    ],
    TEXTO: [
        {'operador': 'contem', 'rotulo': 'contém'},
        {'operador': 'nao_contem', 'rotulo': 'não contém'},
        {'operador': 'comeca_com', 'rotulo': 'começa com'},
        {'operador': 'termina_com', 'rotulo': 'termina com'},
        {'operador': 'e_igual_a', 'rotulo': 'é igual a'},
    ],
    DATA: [
        {'operador': 'nos_ultimos', 'rotulo': 'foi nos últimos', 'unidade': 'dias'},
        {'operador': 'ha_mais_de', 'rotulo': 'foi há mais de', 'unidade': 'dias'},
    ],
    LISTA: [
        {'operador': 'ja_pediu', 'rotulo': 'já pediu'},
        {'operador': 'nunca_pediu', 'rotulo': 'nunca pediu'},
    ],
}


def catalogo() -> list:
    """O que a tela precisa para montar os seletores. Fonte única."""
    return [
        {**campo, 'operadores': [o['operador'] for o in OPERADORES[campo['tipo']]],
         'operadores_detalhe': OPERADORES[campo['tipo']]}
        for campo in CAMPOS
    ]


def _sem_acento(texto: Any) -> str:
    bruto = str(texto or '')
    decomposto = unicodedata.normalize('NFKD', bruto)
    return ''.join(c for c in decomposto if not unicodedata.combining(c)).strip().lower()


def _numero(valor: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _tipo_do_campo(campo: str) -> Optional[str]:
    for c in CAMPOS:
        if c['campo'] == campo:
            return c['tipo']
    return None


def condicao_bate(condicao: Dict[str, Any], perfil: Optional[dict], agora=None) -> bool:
    """Uma condição sobre um perfil. Condição incompleta não derruba: ignora.

    A tela manda condição pela metade o tempo todo enquanto o lojista monta —
    derrubar a prévia a cada tecla seria pior que ignorar.
    """
    campo = condicao.get('campo')
    operador = condicao.get('operador')
    valor = condicao.get('valor')
    if not campo or not operador or valor in (None, '', []):
        return True

    # Quem nunca comprou não tem perfil: nenhuma regra de COMPRA bate nele.
    if perfil is None:
        return False

    tipo = _tipo_do_campo(campo)
    if tipo == NUMERO:
        return _numero_bate(perfil.get(campo), operador, valor)
    if tipo == TEXTO:
        return _texto_bate(perfil.get(campo), operador, valor)
    if tipo == DATA:
        return _data_bate(perfil.get(campo), operador, valor, agora or timezone.now())
    if tipo == LISTA:
        return _lista_bate(perfil.get('produtos') or set(), operador, valor)
    return True


def _numero_bate(atual: Any, operador: str, valor: Any) -> bool:
    a, b = _numero(atual), _numero(valor if not isinstance(valor, (list, tuple)) else valor[0])
    if a is None or b is None:
        return False
    if operador == 'maior_que':
        return a > b
    if operador == 'menor_que':
        return a < b
    if operador == 'e_igual_a':
        return a == b
    if operador == 'entre':
        if not isinstance(valor, (list, tuple)) or len(valor) < 2:
            return False
        fim = _numero(valor[1])
        return fim is not None and b <= a <= fim
    return False


def _texto_bate(atual: Any, operador: str, valor: Any) -> bool:
    a, b = _sem_acento(atual), _sem_acento(valor)
    if operador == 'contem':
        return b in a
    if operador == 'nao_contem':
        return b not in a
    if operador == 'comeca_com':
        return a.startswith(b)
    if operador == 'termina_com':
        return a.endswith(b)
    if operador == 'e_igual_a':
        return a == b
    return False


def _data_bate(atual: Any, operador: str, valor: Any, agora) -> bool:
    dias = _numero(valor)
    if atual is None or dias is None:
        return False
    corte = agora - timedelta(days=int(dias))
    if operador == 'nos_ultimos':
        return atual >= corte
    if operador == 'ha_mais_de':
        return atual < corte
    return False


def _lista_bate(atuais: set, operador: str, valor: Any) -> bool:
    pedidos = {str(v) for v in (valor if isinstance(valor, (list, tuple, set)) else [valor])}
    tem = bool({str(a) for a in atuais} & pedidos)
    if operador == 'ja_pediu':
        return tem
    if operador == 'nunca_pediu':
        return not tem
    return False


def bate(regra: Optional[dict], perfil: Optional[dict], agora=None) -> bool:
    """Grupos somam OU; condições dentro do grupo somam E. Regra vazia = todos."""
    grupos = (regra or {}).get('grupos') or []
    if not grupos:
        return True
    return any(
        all(condicao_bate(c, perfil, agora) for c in (grupo.get('condicoes') or []))
        for grupo in grupos
    )


def _frase_da_condicao(condicao: Dict[str, Any]) -> str:
    campo = condicao.get('campo')
    operador = condicao.get('operador')
    valor = condicao.get('valor')
    rotulo = next((c['rotulo'] for c in CAMPOS if c['campo'] == campo), campo)

    if campo == 'pedidos' and operador == 'maior_que':
        return f'mais de {valor} pedidos'
    if campo == 'ultima_compra' and operador == 'ha_mais_de':
        return f'última compra há mais de {valor} dias'
    if campo == 'ultima_compra' and operador == 'nos_ultimos':
        return f'comprou nos últimos {valor} dias'

    texto_op = next(
        (o['rotulo'] for o in OPERADORES.get(_tipo_do_campo(campo) or '', []) if o['operador'] == operador),
        operador,
    )
    if isinstance(valor, (list, tuple)):
        valor = ' e '.join(str(v) for v in valor)
    return f'{rotulo} {texto_op} {valor}'


def em_portugues(regra: Optional[dict]) -> str:
    """A regra escrita como o lojista falaria — para ele conferir antes de gastar envio."""
    grupos = (regra or {}).get('grupos') or []
    if not grupos:
        return 'Todos os contatos'
    partes = [
        ' e '.join(_frase_da_condicao(c) for c in (g.get('condicoes') or []) if c.get('campo'))
        for g in grupos
    ]
    partes = [p for p in partes if p]
    return ' ou '.join(partes) if partes else 'Todos os contatos'
