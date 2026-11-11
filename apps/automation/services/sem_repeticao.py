"""Saudação e aviso de loja fechada não se repetem para o mesmo cliente em seguida.

19/09: o cliente manda "Olá" e, 2 s depois, "Bom dia" — e recebia duas
saudações (4 vezes em 30 dias; o aviso de loja fechada 1 vez). Não era código
duplicado: cada mensagem era respondida certo, isoladamente.

`cache.add` é atômico: as duas mensagens chegam no mesmo segundo, em workers
diferentes, e só a primeira ganha a trava.
"""
from typing import Optional

from django.core.cache import cache

#: Dez minutos: cobre o "Olá / Bom dia / tudo bem?" em sequência sem impedir
#: uma saudação nova se o cliente voltar mais tarde.
JANELA_SEGUNDOS = 10 * 60

_SAUDACAO = {'greeting', 'welcome'}
_FORA_DO_HORARIO = {'out_of_hours'}


def tipo_repetivel(resposta) -> Optional[str]:
    """'saudacao', 'fora_do_horario' ou None (resposta que pode se repetir)."""
    if resposta is None:
        return None
    meta = getattr(resposta, 'metadata', None) or {}
    marcas = {str(meta.get('intent') or ''), str(meta.get('event_type') or '')}
    if marcas & _SAUDACAO:
        return 'saudacao'
    if marcas & _FORA_DO_HORARIO:
        return 'fora_do_horario'
    return None


def ja_mandou_agora(conversa_id, tipo: str) -> bool:
    """True se este tipo já foi mandado a esta conversa dentro da janela.

    Marca na mesma chamada: quem chega primeiro manda, quem chega em seguida
    recebe True e fica calado.
    """
    chave = f'nao_repetir:{conversa_id}:{tipo}'
    return not cache.add(chave, 1, timeout=JANELA_SEGUNDOS)


# ── Eco de outro robô ────────────────────────────────────────────────────────
#
# 05/nov/2026: uma campanha da Cê Saladas foi para um número que é outro
# assistente automático. Ele respondia "O assistente está disponível apenas
# para lojas selecionadas", o nosso bot respondia, e os dois trocaram 45
# mensagens cada em 12 minutos.
#
# Gente não manda a MESMA frase longa três vezes em dez minutos; robô manda.
# Frase curta ("sim", "ok", "1") repete de verdade num checkout e nunca conta.

#: A partir de quantas vezes a mesma mensagem é eco.
REPETICOES_DE_ECO = 3
#: Abaixo disso a mensagem é curta demais para concluir qualquer coisa.
TAMANHO_MINIMO_DE_ECO = 12


def mensagem_em_eco(conversa_id, texto: str) -> bool:
    """True quando esta conversa recebe a mesma mensagem pela 3ª vez em 10 min."""
    import hashlib

    normalizado = ' '.join((texto or '').lower().split())
    if len(normalizado) < TAMANHO_MINIMO_DE_ECO:
        return False
    digest = hashlib.sha1(normalizado.encode('utf-8')).hexdigest()[:16]
    chave = f'eco:{conversa_id}:{digest}'
    cache.add(chave, 0, timeout=JANELA_SEGUNDOS)
    try:
        vezes = cache.incr(chave)
    except ValueError:  # a chave expirou entre o add e o incr
        cache.add(chave, 1, timeout=JANELA_SEGUNDOS)
        vezes = 1
    return vezes >= REPETICOES_DE_ECO
