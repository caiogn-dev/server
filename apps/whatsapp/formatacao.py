"""Como o bot escreve número para o cliente.

Uma função, um lugar. A regra `.replace('.', ',')` estava copiada em sete
pontos de `intents/handlers/`, e os dois que faltavam eram justamente os da
hora do dinheiro — a confirmação do pedido e a do PIX. Resultado: na mesma
conversa da Dênia (31/08) o mesmo valor saiu "R$ 35,99" no resumo e
"R$ 35.99" na confirmação, quatro minutos depois.
"""
from decimal import Decimal, ROUND_HALF_UP


def moeda(valor, simbolo: bool = True) -> str:
    """Valor em real, como se escreve em português: `R$ 2.384,80`.

    `simbolo=False` devolve só o número, para linha onde o "R$" já veio antes.

    Arredonda meio centavo para cima (ROUND_HALF_UP, o que a pessoa espera),
    não para o par mais próximo — que é o default do Python e faria
    R$ 10,005 virar R$ 10,00.
    """
    try:
        numero = Decimal(str(valor if valor is not None else 0))
    except Exception:
        numero = Decimal('0')
    numero = numero.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # `,` para milhar e `.` para decimal, depois troca os dois de lugar — é o
    # jeito de chegar no formato pt-BR sem depender de locale instalado no
    # container, que não está.
    texto = f'{numero:,.2f}'.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
    return f'R$ {texto}' if simbolo else texto
