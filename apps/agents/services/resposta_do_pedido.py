"""O que o agente do WhatsApp responde depois de `finalizar_pedido`.

`WhatsAppOrderService.create_order_from_cart` devolve o PIX em
`resultado['pix_data']`. A ferramenta lia `resultado.get('pix_code')`, que não
existe: com PIX gerado o cliente não recebia o código, e com PIX falho lia
"PIX sendo gerado" de um PIX que nunca ia chegar.

Função pura para caber num teste — a ferramenta mora dentro de um método que
monta a lista de tools do LangChain.
"""


def _pix(resultado: dict) -> dict:
    pix = resultado.get('pix_data')
    return pix if isinstance(pix, dict) else {}


def resposta_do_pedido_criado(resultado: dict) -> str:
    resultado = resultado or {}
    pedido = resultado.get('order')
    numero = (
        resultado.get('order_number')
        or getattr(pedido, 'order_number', '')
        or ''
    )
    total = resultado.get('total')
    if total is None and pedido is not None:
        total = getattr(pedido, 'total', None)

    linhas = [f"Pedido #{numero} criado!"]
    frete = resultado.get('delivery_fee')
    if frete:
        linhas.append(f"Taxa de entrega: R$ {frete}")
    if total is not None:
        linhas.append(f"Total: R$ {total}")

    pix = _pix(resultado)
    codigo = pix.get('pix_code') if pix.get('success') else ''
    if codigo:
        linhas.append(f"PIX (copia e cola):\n{codigo}")
    else:
        # O motivo real (credencial, gateway fora) fica no log do serviço: ele
        # é da loja, e ao cliente não ajuda. O que ajuda é saber que o pedido
        # existe e o que fazer.
        linhas.append(
            "Seu pedido está salvo, mas não consegui gerar o PIX agora. "
            "A loja vai te chamar para combinar o pagamento."
        )
    return "\n".join(linhas)
