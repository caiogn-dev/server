"""Ler um pedido digitado: o que entra, o que é dúvida, o que é recado.

Era trabalho do extrator do handler `create_order`, que escolhia sozinho o
primeiro produto que coubesse na frase. Em 25/09 ele lançou 1× Cebola roxa
para quem escreveu "sem cebola roxa" (CE-2609251646). A leitura agora usa o
MESMO casamento da triagem (`candidatos_pontuados`) e devolve três coisas:

- `itens`: trechos com UM vencedor claro, com a quantidade dita;
- `duvidas`: trechos em que dois ou mais produtos empatam no topo — quem fala
  com o cliente pergunta "qual destes?" em vez de chutar;
- `notas`: "sem …" e "acrescenta …", com a grafia do cliente.

Não escreve nada: quem grava carrinho continua sendo o handler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.stores.services.busca_de_produto import (
    _ACRESCIMOS, candidatos_pontuados, normalizar, separar_negacoes, trechos_de_acrescimo,
)

_NUMEROS_ESCRITOS = {'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3, 'quatro': 4,
                     'cinco': 5, 'seis': 6}
_QUANTIDADE = re.compile(r'\b(\d{1,2})\s*x?\b')


@dataclass
class Leitura:
    itens: list = field(default_factory=list)      # [(produto|combo, quantidade)]
    duvidas: list = field(default_factory=list)    # [([candidatos empatados], quantidade)]
    notas: list = field(default_factory=list)      # ['sem tomate cereja', …]


def _eh_acrescimo(trecho: str) -> bool:
    """"acrescenta cenoura" é recado; "coloca 2 sucos" é pedido (tem quantidade)."""
    alvo = normalizar(trecho)
    return any(v in alvo for v in _ACRESCIMOS) and not _QUANTIDADE.search(alvo)


def _trechos_que_pedem(texto: str) -> list[str]:
    pede, _ = separar_negacoes(texto)
    trechos = []
    for oracao in re.split(r'[,.;!?\n+]', pede):
        if _eh_acrescimo(oracao):
            continue
        trechos.extend(t for t in re.split(r'\s+e\s+', oracao, flags=re.IGNORECASE) if t.strip())
    return trechos


def parte_que_pede(texto: str) -> str:
    """A frase sem o que o cliente tira nem o que ele pede para acrescentar."""
    return ', '.join(t.strip() for t in _trechos_que_pedem(texto))


def _quantidade(trecho: str, nome: str) -> int:
    """Número dito antes do produto; o que faz parte do nome ("Combo 5") não conta."""
    alvo = normalizar(trecho)
    do_nome = set(normalizar(nome).split())
    for m in _QUANTIDADE.finditer(alvo):
        if m.group(1) not in do_nome and 1 <= int(m.group(1)) <= 50:
            return int(m.group(1))
    for palavra in alvo.split():
        if palavra in _NUMEROS_ESCRITOS and palavra not in do_nome:
            return _NUMEROS_ESCRITOS[palavra]
    return 1


def ler_pedido(store, texto: str) -> Leitura:
    _, negados = separar_negacoes(texto)
    leitura = Leitura(notas=negados + [t for t in trechos_de_acrescimo(texto)
                                       if t not in negados and _eh_acrescimo(t)])
    vistos = set()
    for trecho in _trechos_que_pedem(texto):
        pontuados = candidatos_pontuados(store, trecho)
        if not pontuados:
            continue
        topo = pontuados[0][1]
        empatados = [o for o, pontos in pontuados if pontos == topo][:3]
        chave = tuple(sorted(str(o.id) for o in empatados))
        if chave in vistos:
            # "Arroz e feijão" partido no " e " casa o mesmo produto duas vezes.
            continue
        vistos.add(chave)
        quantidade = _quantidade(trecho, empatados[0].name)
        if len(empatados) == 1:
            leitura.itens.append((empatados[0], quantidade))
        else:
            leitura.duvidas.append((empatados, quantidade))
    return leitura
