"""Catálogo vivo: qual modelo pode ser pedido à NVIDIA NIM hoje.

POR QUE ESTE MÓDULO EXISTE

QUATRO vezes em oito semanas o modelo default do sistema foi aposentado pelo
provedor e o sintoma chegou como degradação silenciosa:

    15/jul/2026  meta/llama-3.1-405b-instruct   saiu do catálogo
    26/ago/2026  meta/llama-3.1-70b-instruct    410 Gone
    01/set/2026  nvidia/nemotron-3-nano-30b-a3b 410 Gone (às 09:00 UTC)
    03/set/2026  openai/gpt-oss-120b            410 Gone (às 08:00 UTC)

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

POR QUE PERGUNTAR AO PROVEDOR, E NÃO SÓ MANTER UMA LISTA

As três primeiras correções fizeram a mesma coisa: apontar o default para o
próximo nome, à mão. Em 03/set isso cobrou a conta — o substituto escolhido
dois dias antes morreu, e a escada de fallback passou a apontar para uma
lápide. O modelo pedido dava 410 e o substituto TAMBÉM: a IA caiu inteira, e
o padrão só quebrou porque o segundo andar da escada estava podre.

Uma lista fixa de nomes bons é, por construção, uma lista que envelhece. Quem
sabe o que está vivo é o provedor, e ele responde isso em `/v1/models`.

A divisão de trabalho: a ORDEM da preferência é humana e vem de MEDIÇÃO com o
prompt real do painel — velocidade e JSON válido não se adivinham pelo nome.
Quem está morto é o provedor quem diz. Assim a próxima morte vira uma resposta
um pouco pior, escolhida sozinha, em vez de uma tela vazia por dois dias.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: Quanto tempo a listagem do provedor vale. Modelo não morre de hora em hora,
#: e uma chamada HTTP por pedido de modelo seria absurdo.
CATALOGO_TTL_SEGUNDOS = 6 * 60 * 60
_CHAVE_DE_CACHE = 'nim:catalogo-de-modelos'

#: Modelos que a NIM já enterrou. Pedir qualquer um devolve 410/404.
#: Quando o próximo morrer, some a linha aqui: os testes que fixam o default
#: quebram na hora e obrigam quem mexer a escolher o substituto.
MODELOS_APOSENTADOS = frozenset({
    'meta/llama-3.1-405b-instruct',
    'meta/llama-3.1-70b-instruct',
    'meta/llama-3.1-8b-instruct',
    'nvidia/nemotron-3-nano-30b-a3b',
    'openai/gpt-oss-120b',
})

#: Ordem de preferência, MEDIDA — não escolhida pelo nome. Medição de
#: 04/set/2026 contra o catálogo real com o prompt DE VERDADE do painel
#: (stats + forecast da Cê Saladas), 3 tentativas cada:
#:
#:   nvidia/nemotron-3-super-120b-a12b   3/3 JSON válido   12,7s  ← padrão
#:   openai/gpt-oss-20b                  3/3 JSON válido   69,5s  (23s por
#:                                                          chamada: só serve
#:                                                          como último recurso)
#:   nvidia/nemotron-3.5-lightning-30b   0/3               38,3s  (não devolve
#:                                                          JSON — fora)
#:   nvidia/nemotron-nano-3-30b-a3b      404 para a conta         (fora)
#:
#: `openai/gpt-oss-*` é modelo de PESO ABERTO servido pela própria NVIDIA NIM
#: — mesma chave, mesma base_url, mesmo endpoint. Não é a API da OpenAI, e
#: trocar para ela seria mudar de provedor, o que este sistema não faz.
PREFERENCIA = (
    'nvidia/nemotron-3-super-120b-a12b',
    'openai/gpt-oss-20b',
)

#: O primeiro da preferência. Existe como nome próprio porque muito código
#: antigo importa `MODELO_PADRAO`; a fonte da verdade é `PREFERENCIA`.
MODELO_PADRAO = PREFERENCIA[0]

#: Famílias que raciocinam antes de responder. Com `thinking` ligado o
#: raciocínio consome o orçamento de `max_tokens` ANTES da resposta e o JSON
#: chega truncado — medido: JSON quebrado a 10s ligado, 4/4 válidos a 3,7s
#: desligado.
FAMILIAS_COM_RACIOCINIO = ('nemotron-3-nano', 'nemotron-3-super', 'nemotron-3-ultra')


def _buscar_catalogo() -> frozenset[str]:
    """Os modelos que o provedor diz servir agora. Só faz a chamada HTTP."""
    import json
    import urllib.request

    chave = os.environ.get('NVIDIA_API_KEY') or os.environ.get('NIM_API_KEY') or ''
    # O nome da variável é `NVIDIA_API_BASE_URL` (é assim no compose e no
    # .env). `NVIDIA_BASE_URL` fica como segunda chance para não quebrar em
    # ambiente que use o nome curto.
    base = (
        os.environ.get('NVIDIA_API_BASE_URL')
        or os.environ.get('NVIDIA_BASE_URL')
        or 'https://integrate.api.nvidia.com/v1'
    ).rstrip('/')
    req = urllib.request.Request(
        f'{base}/models', headers={'Authorization': f'Bearer {chave}'},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        dados = json.load(r)
    return frozenset(
        str(m['id']) for m in (dados.get('data') or []) if m.get('id')
    )


def catalogo_vivo() -> frozenset[str] | None:
    """O catálogo do provedor, cacheado. `None` = não deu para saber.

    `None` e conjunto vazio são coisas diferentes e viram a mesma resposta de
    propósito: uma listagem vazia é resposta estranha do provedor, não "tudo
    morreu". Tratá-la como verdade reprovaria TODO modelo e derrubaria a IA —
    exatamente o que este módulo existe para evitar.
    """
    from django.core.cache import cache

    try:
        guardado = cache.get(_CHAVE_DE_CACHE)
        if guardado is not None:
            return guardado or None

        catalogo = _buscar_catalogo()
        if not catalogo:
            return None
        cache.set(_CHAVE_DE_CACHE, catalogo, CATALOGO_TTL_SEGUNDOS)
        return catalogo
    except Exception as exc:
        # Falha aberta: listagem fora do ar não pode derrubar a IA que ainda
        # funcionaria. O chamador cai no comportamento estático.
        logger.warning('[modelos] não consegui listar o catálogo do provedor: %s', exc)
        return None


def esquecer_catalogo() -> None:
    """Descarta o cache do catálogo. Para testes e para forçar releitura."""
    try:
        from django.core.cache import cache
        cache.delete(_CHAVE_DE_CACHE)
    except Exception:
        pass


def modelo_vivo(nome: str | None, padrao: str = MODELO_PADRAO) -> str:
    """O melhor modelo que EXISTE HOJE, dado o que foi pedido.

    Nunca levanta: um modelo aposentado é problema de configuração, e derrubar
    a requisição por isso troca "resposta pior" por "tela quebrada".
    """
    escolhido = (nome or '').strip()
    try:
        catalogo = catalogo_vivo()
    except Exception:
        catalogo = None

    if catalogo:
        if escolhido and escolhido in catalogo:
            return escolhido
        for candidato in PREFERENCIA:
            if candidato in catalogo:
                if escolhido:
                    logger.warning(
                        '[modelos] %s não está no catálogo do provedor; usando %s',
                        escolhido, candidato,
                    )
                return candidato
        # Nenhuma preferência viva: o provedor mudou de nomenclatura inteira.
        # Segue com o pedido e deixa o erro real aparecer, que é mais honesto
        # que escolher um nome inventado.
        logger.error(
            '[modelos] NENHUM modelo preferido está no catálogo (%d disponíveis). '
            'Alguém precisa medir e reescolher a PREFERENCIA.', len(catalogo),
        )
        return escolhido or padrao

    # Sem catálogo: a lista estática é a única defesa que resta.
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
