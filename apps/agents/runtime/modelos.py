"""Catálogo vivo: qual modelo pode ser pedido à NVIDIA NIM hoje.

POR QUE ESTE MÓDULO EXISTE

TRÊS vezes em sete semanas o modelo default do sistema foi aposentado pelo
provedor e o sintoma chegou como degradação silenciosa:

    15/jul/2026  meta/llama-3.1-405b-instruct   saiu do catálogo
    26/ago/2026  meta/llama-3.1-70b-instruct    410 Gone
    01/set/2026  nvidia/nemotron-3-nano-30b-a3b 410 Gone (às 09:00 UTC)

Na segunda vez o painel ficou DOIS DIAS estampando "gerado sem IA" enquanto o
erro existia apenas como WARNING no log do container. Ninguém olha WARNING de
container; todo mundo olha a tela. Na terceira o dono percebeu no mesmo dia —
"a IA parece que não tá funcionando" — o que é melhor, mas ainda é o cliente
descobrindo antes do sistema.

POR QUE FILTRAR EM CÓDIGO E NÃO SÓ CORRIGIR O `.env`

O env de produção vive assado dentro da imagem (`docker commit`), e trocá-lo
exige recriar o container — o que, pela regra do deploy da casa, apaga os
`docker cp` anteriores. Enquanto isso `NVIDIA_MODEL_NAME` continua apontando
para a lápide e qualquer caminho que caia no default do env volta a falhar.
Filtrar aqui faz a correção valer mesmo com o env velho no lugar.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Modelos que a NIM já enterrou. Pedir qualquer um devolve 410/404.
#: Quando o próximo morrer, some a linha aqui: os testes que fixam o default
#: quebram na hora e obrigam quem mexer a escolher o substituto.
MODELOS_APOSENTADOS = frozenset({
    'meta/llama-3.1-405b-instruct',
    'meta/llama-3.1-70b-instruct',
    'meta/llama-3.1-8b-instruct',
    'nvidia/nemotron-3-nano-30b-a3b',
})

#: Escolhido medindo contra o catálogo real de 01/set/2026 com o prompt DE
#: VERDADE do painel (stats + forecast da Cê Saladas), não pelo nome:
#:
#:   openai/gpt-oss-120b            3/3 JSON válido   5,2s  ← escolhido
#:   nemotron-3-super-120b-a12b     3/3 JSON válido   9,6s
#:   openai/gpt-oss-20b             3/3 JSON válido  13,9s
#:   nemotron-3.5-lightning-30b     0/3              47,4s
#:   nemotron-nano-3-30b-a3b        404 para a conta        (sucessor de nome
#:                                                           trocado, não liberado)
#:
#: ATENÇÃO ao nome: `openai/gpt-oss-120b` é um modelo de PESO ABERTO servido
#: pela própria NVIDIA NIM — mesma chave, mesma base_url, mesmo endpoint. Não
#: é a API da OpenAI, e trocar para ela seria mudar de provedor, o que este
#: sistema não faz.
MODELO_PADRAO = 'openai/gpt-oss-120b'

#: Famílias que raciocinam antes de responder. Com `thinking` ligado o
#: raciocínio consome o orçamento de `max_tokens` ANTES da resposta e o JSON
#: chega truncado — medido: JSON quebrado a 10s ligado, 4/4 válidos a 3,7s
#: desligado.
FAMILIAS_COM_RACIOCINIO = ('nemotron-3-nano', 'nemotron-3-super', 'nemotron-3-ultra')


def modelo_vivo(nome: str | None, padrao: str = MODELO_PADRAO) -> str:
    """Devolve `nome` se ele ainda existe no catálogo; senão, o padrão.

    Nunca levanta: um modelo aposentado é problema de configuração, e derrubar
    a requisição por isso troca "resposta pior" por "tela quebrada".
    """
    escolhido = (nome or '').strip()
    if not escolhido:
        return padrao
    if escolhido in MODELOS_APOSENTADOS:
        logger.warning(
            '[modelos] %s está aposentado no provedor; usando %s no lugar',
            escolhido, padrao,
        )
        return padrao
    return escolhido


def corpo_extra_do_modelo(model_name: str | None) -> dict:
    """Parâmetros fora do padrão OpenAI que este modelo exige.

    Só a família que raciocina recebe a chave: mandar `chat_template_kwargs`
    para quem não a entende é convite a 400 — e um 400 aqui reproduz
    exatamente a falha que este módulo conserta.
    """
    if any(f in (model_name or '') for f in FAMILIAS_COM_RACIOCINIO):
        return {'chat_template_kwargs': {'thinking': False}}
    return {}
