"""O link que carrega QUEM indicou.

O CASO REAL (04/09): a Elisangela tocou em "🎁 Indicar um amigo" e recebeu do
bot a mensagem pronta para encaminhar:

    10% de desconto no primeiro pedido na Cê Saladas!
    Usa o cupom *INDICA10* em https://cesaladas.com.br

Nada ali é dela. `INDICA10` é FIXO e igual para todos — de propósito, porque
código pessoal já foi tentado aqui (13 AVALIA5-XXXXXX criados, 0 usados:
ninguém digita hash no carrinho) — e o link ia pelado. A amiga compra, ganha os
10%, e o cashback da Elisangela não sai: o backend não tem de quem creditar.

Quem carrega a identidade é o LINK. O storefront guarda o `?indica=` por 30
dias no navegador do amigo, e ele viaja com o pedido virando
`metadata.indicado_por`.

DUAS ARMADILHAS QUE ESTA FUNÇÃO EXISTE PARA FECHAR:

1. O ENDEREÇO É O DO CARDAPIDEX, nunca o domínio próprio da loja.
   `cesaladas.com.br` é OUTRO APP (buildId diferente do cardapidex-web) e a
   captura do `?indica=` não existe lá. Mandar a indicação para o domínio
   próprio é mandar para um lugar que não sabe ler o parâmetro: o link parece
   certo, o amigo compra, e o crédito nunca sai. Silencioso, que é o pior modo
   de falha quando envolve dinheiro.

2. O TELEFONE É O DO PEDIDO, normalizado. O crédito casa por string lá na
   frente; um número em formato diferente do cadastro some sem erro nenhum.
"""
from django.conf import settings

from apps.core.utils import normalize_phone_number

#: O storefront multi-tenant — o único que lê `?indica=`.
BASE_PADRAO = 'https://cardapidex.com.br'


def link_de_indicacao(store, telefone: str) -> str:
    """`https://cardapidex.com.br/<slug>?indica=<telefone>`.

    Sem telefone válido devolve o cardápio sem o parâmetro: melhor um link que
    vende do que link nenhum — mas nunca um link que finge rastrear.
    """
    base = str(
        getattr(settings, 'STOREFRONT_BASE_URL', '') or BASE_PADRAO
    ).rstrip('/')
    url = f'{base}/{store.slug}'
    numero = normalize_phone_number(telefone or '')
    return f'{url}?indica={numero}' if numero else url
