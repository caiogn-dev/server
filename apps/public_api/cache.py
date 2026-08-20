"""Cache de borda para os endpoints públicos do cardápio.

Medido em 19/08 contra produção:

    catálogo dentro do container:  0,054s – 0,067s
    catálogo pela internet:        0,87s típico, com picos de 4,4s e 6,3s

O Django é rápido; o custo é o túnel. E como nenhuma resposta trazia
`Cache-Control`, o Cloudflare marcava tudo como DYNAMIC e **todo cliente que
abria o cardápio pagava o pedágio inteiro, toda vez**.

Regras que valem a pena registrar:

- `s-maxage` só governa cache COMPARTILHADO (Cloudflare). O navegador continua
  revalidando. É isso que permite o lojista editar um produto e ver a mudança
  no próprio painel sem esperar o TTL.
- `stale-while-revalidate` faz a borda servir a cópia velha ENQUANTO busca a
  nova. Quem chega depois do TTL não paga a espera; o pico de 6s some da
  experiência do cliente.
- Só entra aqui endpoint que é igual para todo mundo. Nada que dependa de
  usuário, sessão ou carrinho — resposta personalizada em cache compartilhado
  vaza dado de um cliente para outro.
- Disponibilidade (loja aberta/fechada) fica FORA de propósito: muda de minuto
  a minuto e mostrar "aberto" para uma loja fechada custa pedido perdido.
"""
from functools import wraps

#: Curto porque preço muda: a promoção por dia da semana vira à meia-noite e o
#: lojista pausa produto no meio do movimento. 60s é o mesmo TTL que o
#: storefront já usa no Next (s-maxage=60).
TTL_PADRAO = 60
JANELA_STALE = 300


def cache_publico(segundos: int = TTL_PADRAO, stale: int = JANELA_STALE):
    """Marca a resposta como cacheável pela borda (não pelo navegador)."""
    def decorador(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            resposta = view(request, *args, **kwargs)
            # Só resposta boa vira cache: guardar 404/500 na borda multiplica
            # o estrago de um erro momentâneo por todo o TTL.
            if 200 <= getattr(resposta, 'status_code', 500) < 300:
                resposta['Cache-Control'] = (
                    f'public, s-maxage={segundos}, stale-while-revalidate={stale}'
                )
            return resposta
        return wrapper
    return decorador
