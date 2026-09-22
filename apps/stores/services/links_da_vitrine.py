"""Endereço canônico de uma página INTERNA da vitrine.

Em 21/09 o convite de avaliação apontava para `https://cesaladas.com.br/orders/
<token>` e respondia **404**. O mesmo caminho em
`https://cardapidex.com.br/ce-saladas/orders/<token>` responde 200: o domínio
próprio da loja serve a home e alguns caminhos, não todos. Como o convite leva
justamente para `/orders`, TODO convite apontava para o vazio — e é por isso
que das 81 avaliações só 2 têm comentário.

A regra que este módulo carrega: a VITRINE que a loja divulga pode ter domínio
próprio; o LINK INTERNO que o sistema manda usa o canônico, que serve tudo.

`CheckoutService.get_storefront_base_url` continua existindo e continua certa
para o que ela faz — voltar do pagamento para onde o cliente estava.
"""
from django.conf import settings


def link_da_vitrine(store, caminho: str = '') -> str:
    """`https://cardapidex.com.br/<slug>/<caminho>`."""
    base = (getattr(settings, 'STOREFRONT_BASE_URL', '') or 'https://cardapidex.com.br').rstrip('/')
    slug = (getattr(store, 'slug', '') or '').strip('/')
    caminho = (caminho or '').strip('/')
    partes = [p for p in (base, slug, caminho) if p]
    return '/'.join(partes)
