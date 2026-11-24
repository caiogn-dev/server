"""Status mudado no painel do iFood ou da 99 → o nosso painel acompanha.

Pedido do dono (24/11): marcou "despachado" no Gestor de Pedidos do iFood e o
painel ficou em "preparando".

Duas regras:
- só AVANÇA (preparo → pronto → saiu → entregue). O aviso pode chegar atrasado
  ou ser o eco de algo que o próprio painel já fez; voltar o status desfaria o
  trabalho da cozinha. Cancelado/entregue não mudam por aqui.
- SEM ECO: usa `StoreOrder.update_status(notify=False)`, não o
  `order_service.update_status` — é este que manda o status de volta à
  plataforma (avisar_status_depois). Disparo de entregador também fica de fora:
  Toca só no `confirmed`, iFood Entrega ignora pedido de iFood/99.
"""
from __future__ import annotations

_ORDEM = {
    'pending': 0, 'processing': 0, 'paid': 0, 'confirmed': 0,
    'preparing': 1, 'ready': 2, 'shipped': 3, 'out_for_delivery': 3,
    'delivered': 4, 'completed': 4,
}
_FINAIS = {'delivered', 'completed', 'cancelled', 'refunded', 'failed'}


def avancar(pedido, novo: str) -> bool:
    """Leva o pedido para `novo` se for um passo à frente. True se mudou."""
    atual = pedido.status
    if atual in _FINAIS or novo not in _ORDEM:
        return False
    if _ORDEM[novo] <= _ORDEM.get(atual, 0):
        return False
    pedido.update_status(novo, notify=False)
    return True
