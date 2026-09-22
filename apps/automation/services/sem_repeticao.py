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
