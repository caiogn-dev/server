"""Avisa o cardápio (cardapidex-web) que o catálogo de uma loja mudou.

Sem isto, preço/destaque/promoção levavam ~3 min para aparecer: o server2 já
apagava o próprio cache no save, mas a página pré-gerada do cardápio e a
Cloudflare só se atualizavam quando o prazo delas vencia E alguém visitava.

O aviso só sai depois do commit (dado desfeito não pode virar página) e uma
janela curta junta os saves em rajada — editar o cardápio inteiro dispara um
aviso, não cinquenta. A tarefa roda no fim da janela, quando todos já
commitaram.
"""
from django.core.cache import cache
from django.db import transaction

from apps.stores.tasks import revalidar_cardapio

JANELA_S = 2


def avisar_que_o_cardapio_mudou(slug):
    if not slug:
        return

    def _depois_do_commit():
        if cache.add(f'cardapio:aviso:{slug}', 1, timeout=JANELA_S):
            revalidar_cardapio.apply_async(args=[slug], countdown=JANELA_S)

    transaction.on_commit(_depois_do_commit)
