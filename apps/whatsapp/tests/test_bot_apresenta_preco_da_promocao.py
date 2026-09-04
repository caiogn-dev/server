"""O bot tem que MOSTRAR a promoção do dia, não só cobrá-la.

O CASO REAL (04/09, sexta): a Tilápia Suprema custa R$ 46,99 e está a
R$ 31,99 às sextas. Um cliente perguntou pelo WhatsApp e o bot respondeu
"R$ 46,99". Ele não comprou. O dono: "PERDI UMA VENDA PQ ELE APRESENTOU O
PREÇO 46,99".

A raiz é a metade que ficou de fora da correção de 02/09. Naquele dia
`preco_vigente()` entrou em todos os caminhos que COBRAM — pedido do painel,
PDV, `unit_price` do bot. Os caminhos que APRESENTAM continuaram lendo
`product.price` cru: cardápio, busca por nome, lista interativa, resumo do
carrinho, seletor de quantidade e o cardápio que vai no prompt do LLM.

O efeito é pior que cobrar errado. Cobrar caro o cliente reclama e a loja
conserta; anunciar caro ele some calado, e ninguém fica sabendo que a
promoção existia. A promoção do dia é justamente o que faz ele comprar.

Este arquivo é uma PENEIRA de código-fonte, não só de comportamento. É a
terceira vez que `.price` cru reaparece em um caminho de preço neste projeto,
sempre em código novo escrito longe de quem conhecia a regra. Teste de
comportamento só pega a função que ele visita; a peneira pega o arquivo
inteiro, inclusive a função que alguém adicionar amanhã.
"""
import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[3]

# Os arquivos que falam preço COM O CLIENTE — no WhatsApp e no prompt do LLM.
ARQUIVOS_QUE_ANUNCIAM_PRECO = [
    'apps/whatsapp/intents/handlers/catalog.py',
    'apps/whatsapp/intents/handlers/interactive.py',
    'apps/whatsapp/intents/handlers/base.py',
    'apps/agents/graph/nodes.py',
    'apps/agents/services/langchain_service.py',
    'apps/automation/services/unified_service.py',
]

# `price` é legítimo em COMBO (não tem promoção por dia de semana) e nos nomes
# compostos do próprio código (`unit_price`, `total_price`). O que não pode é
# ler o atributo `.price` de um PRODUTO para dizer ao cliente quanto custa.
DONOS_DE_PRECO_FIXO = {'combo', 'c', 'plano', 'pacote'}


def _leituras_cruas_de_price(caminho: pathlib.Path):
    """Todo `<algo>.price` do arquivo, menos os donos de preço fixo."""
    arvore = ast.parse(caminho.read_text(encoding='utf-8'))
    achados = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Attribute) and no.attr == 'price'):
            continue
        dono = no.value
        nome = dono.id if isinstance(dono, ast.Name) else getattr(dono, 'attr', '?')
        if nome.lower() in DONOS_DE_PRECO_FIXO:
            continue
        achados.append(f'{nome}.price (linha {no.lineno})')
    return achados


@pytest.mark.parametrize('arquivo', ARQUIVOS_QUE_ANUNCIAM_PRECO)
def test_nenhum_caminho_de_bot_anuncia_price_cru(arquivo):
    caminho = RAIZ / arquivo
    assert caminho.exists(), f'{arquivo} sumiu — a peneira precisa ser atualizada'

    cruas = _leituras_cruas_de_price(caminho)

    assert not cruas, (
        f'{arquivo} lê o preço de tabela direto: {", ".join(cruas)}.\n'
        'Use preco_vigente(), que resolve a promoção do dia. Ler `price` aqui '
        'faz o bot anunciar R$ 46,99 numa sexta em que a Tilápia sai a R$ 31,99 '
        '— e o cliente vai embora sem dizer nada.'
    )
