"""Código de barras interno para produto sem código de fabricante.

A maioria do que estas lojas vendem é feito na cozinha e não tem EAN de
indústria: em 12/ago o Agrião tinha 0 de 47 produtos com código, a Cê Saladas
1 de 35, a Ivoneth 0 de 45. Sem código, a etiqueta não fecha e o leitor do
balcão não serve para nada.

**Por que EAN-13 começando com 2.** O GS1 reserva o prefixo 2 para uso interno
de estabelecimento. Duas consequências práticas: o código nunca colide com o
de um produto de indústria (que nunca começa com 2), e qualquer leitor de
código de barras lê nativamente, sem configuração nenhuma no equipamento — o
que importa quando o operador está com fila na frente.

A "Queridinha" da Cê Saladas já usava `2411661232460`, então isto padroniza
uma convenção que a loja começou, em vez de inventar uma terceira.
"""

FAIXA_INTERNA = '2'
"""Prefixo reservado pelo GS1 para uso interno da loja."""


def digito_verificador_ean13(doze_digitos: str) -> int:
    """Calcula o 13º dígito a partir dos 12 primeiros.

    Pesos alternados 1 e 3 da direita para a esquerda, e o verificador é o que
    falta para a próxima dezena. É a mesma conta que o leitor refaz ao ler —
    errar aqui produz um código que existe no banco e o scanner recusa.
    """
    if len(doze_digitos) != 12 or not doze_digitos.isdigit():
        raise ValueError('EAN-13 precisa de exatamente 12 dígitos antes do verificador.')
    soma = sum(
        int(digito) * (3 if posicao % 2 else 1)
        for posicao, digito in enumerate(doze_digitos)
    )
    return (10 - soma % 10) % 10


def valido_ean13(codigo: str) -> bool:
    """Confere se um código de 13 dígitos fecha com o próprio verificador."""
    if not codigo or len(codigo) != 13 or not codigo.isdigit():
        return False
    return digito_verificador_ean13(codigo[:12]) == int(codigo[12])


def gerar_codigo_interno(loja: int, sequencial: int) -> str:
    """Monta o código de uma loja/posição.

    Layout dos 12 dígitos de dados: `2` + loja (2) + sequencial (9).
    Determinístico de propósito: o mesmo par sempre devolve o mesmo código,
    então rodar o comando de novo não inventa código novo para quem já tem
    etiqueta impressa na prateleira.
    """
    if not 1 <= loja <= 99:
        raise ValueError('Número da loja precisa estar entre 1 e 99.')
    if not 0 <= sequencial <= 999_999_999:
        raise ValueError('Sequencial fora da faixa de 9 dígitos.')
    dados = f'{FAIXA_INTERNA}{loja:02d}{sequencial:09d}'
    return f'{dados}{digito_verificador_ean13(dados)}'
