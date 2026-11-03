"""Ocasião do pedido — para quê o cliente está encomendando.

Sugestão do atendente da Ivoneth (03/11): o mesmo coffee de 30 pessoas pede
capricho diferente numa reunião de firma e no aniversário de 60 anos da mãe.
A pergunta é opcional e só existe na loja que ligar `metadata.perguntar_ocasiao`.

Lista fechada de propósito: texto livre não vira segmento de cliente, e a
cozinha precisa ler a mesma palavra em toda comanda.
"""
from __future__ import annotations

import unicodedata

CHAVE_DA_LOJA = 'perguntar_ocasiao'
CHAVE_DO_PEDIDO = 'ocasiao'

# (valor, rótulo na tela do cliente, rótulo na comanda)
_OCASIOES = (
    ('aniversario', 'Aniversário', 'Aniversário'),
    ('meu_aniversario', 'Meu aniversário', 'Aniversário do próprio cliente'),
    ('reuniao', 'Reunião ou empresa', 'Reunião ou empresa'),
    ('casamento', 'Casamento', 'Casamento'),
    ('cha', 'Chá de bebê ou revelação', 'Chá de bebê ou revelação'),
    ('religioso', 'Batizado ou religioso', 'Batizado ou evento religioso'),
    ('formatura', 'Formatura', 'Formatura'),
    ('outro', 'Outra ocasião', 'Outra ocasião'),
)
_POR_VALOR = {valor: (tela, comanda) for valor, tela, comanda in _OCASIOES}


def opcoes() -> list[dict]:
    return [{'valor': valor, 'rotulo': tela} for valor, tela, _ in _OCASIOES]


def pergunta_ligada(store) -> bool:
    metadata = getattr(store, 'metadata', None)
    return bool(isinstance(metadata, dict) and metadata.get(CHAVE_DA_LOJA) is True)


def ocasiao_valida(store, valor) -> str:
    """O valor que pode ir para o pedido, ou '' (loja desligada, vazio, lixo).
    Nunca levanta: a ocasião não derruba venda."""
    if not pergunta_ligada(store) or not isinstance(valor, str):
        return ''
    limpo = valor.strip().lower()
    return limpo if limpo in _POR_VALOR else ''


def _sem_acento(texto: str) -> str:
    # Agentes de impressão antigos mandam o texto cru para a térmica, que não
    # tem tabela de acentos (mesmo motivo do "cartao" do aviso da maquininha).
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')


def para_comanda(valor) -> str:
    rotulos = _POR_VALOR.get(valor) if isinstance(valor, str) else None
    if not rotulos:
        return ''
    return f'OCASIAO: {_sem_acento(rotulos[1])}'
