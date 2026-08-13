"""Decidir o que a pessoa quer, ANTES de olhar o estado da conversa.

Nasceu da conversa da Yeda com a Cê Saladas (13/ago), onde o bot custou um
pedido: ela escreveu "Quero salada" enquanto o fluxo esperava observação,
recebeu "✅ Anotado: Quero salada", e o pedido fechou com R$ 20 em vez de
R$ 100 — a dona teve que cancelar e refazer na mão.

A causa não era falta de inteligência, era ORDEM. O estado da conversa era
consultado antes da intenção, então quem estava "esperando observação"
transformava qualquer texto em observação. Aqui a ordem se inverte: primeiro se
decide o que a pessoa quis dizer; o estado entra depois, como desempate.

## O que este módulo é, e o que não é

É um **classificador**. Ele devolve uma `Decisao` e não escreve nada — nem
carrinho, nem sessão, nem pedido. Quem executa continua sendo o handler
determinístico, que é onde preço, frete e criação de pedido têm que viver.

A ordem interna é deliberada:

1. **Regex e catálogo primeiro.** "oi", "cardápio", nome de produto — resolve em
   milissegundos, sem custo. O bot já teve 3 minutos de latência e mensagem
   descartada no timeout de 90s; o caminho quente não pode passar por modelo.
2. **LLM só no que sobrou** — e injetado, para que todo teste rode sem modelo.
3. **Falha nunca vira silêncio.** Timeout, exceção ou resposta malformada caem
   no determinístico. "Silêncio nunca é o desfecho aceitável" é a regra que
   este projeto vem pagando caro para aprender.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

import logging

logger = logging.getLogger(__name__)


class Intencao(Enum):
    SAUDACAO = 'saudacao'
    ITEM = 'item'                # quer acrescentar algo ao pedido
    OBSERVACAO = 'observacao'    # recado para a cozinha
    CONSULTIVA = 'consultiva'    # pergunta que merece resposta em texto
    VAZIA = 'vazia'


#: Palavras que são saudação e nada mais. Curta de propósito: qualquer coisa
#: além disso é trabalho do regex completo do detector, que já existe.
_SAUDACOES = {
    'oi', 'ola', 'olá', 'bom dia', 'boa tarde', 'boa noite', 'oie', 'eae',
    'e ai', 'e aí', 'opa', 'hey', 'hi',
}


@dataclass
class Decisao:
    """O que a triagem entendeu. Sem efeito colateral, por contrato."""

    intencao: Intencao = Intencao.CONSULTIVA
    itens: List[object] = field(default_factory=list)
    texto: str = ''
    confianca: float = 1.0
    origem: str = 'deterministico'

    @property
    def precisa_de_resposta(self) -> bool:
        return self.intencao is not Intencao.VAZIA


def triar(
    mensagem: str,
    *,
    store=None,
    esperando: Optional[str] = None,
    classificador: Optional[Callable] = None,
) -> Decisao:
    """Classifica a mensagem.

    `esperando` é o estado do checkout ('observacao', 'endereco' ou None). Ele
    entra como DESEMPATE, nunca como atalho: é o que impede o estado de engolir
    um pedido de produto.
    """
    texto = (mensagem or '').strip()
    if not texto:
        return Decisao(intencao=Intencao.VAZIA)

    from apps.stores.services.busca_de_produto import normalizar, tem_negacao

    normalizado = normalizar(texto)

    if normalizado in _SAUDACOES:
        return Decisao(intencao=Intencao.SAUDACAO, texto=texto)

    # Negação é observação mesmo quando casa com produto. A Cê Saladas vende
    # ingrediente avulso, então "sem cebola" — o exemplo que o próprio bot dá —
    # casa com o produto "Cebola roxa".
    if tem_negacao(texto):
        if esperando == 'observacao':
            return Decisao(intencao=Intencao.OBSERVACAO, texto=texto)
        return Decisao(intencao=Intencao.CONSULTIVA, texto=texto)

    achados = _produtos(store, texto)
    if achados:
        # A lista inteira segue adiante: com mais de um candidato, quem fala com
        # o cliente pergunta "qual delas?" em vez de escolher no chute.
        return Decisao(
            intencao=Intencao.ITEM, itens=achados, texto=texto,
            confianca=1.0 if len(achados) == 1 else 0.5,
        )

    if classificador is not None:
        decisao = _perguntar_ao_modelo(classificador, texto, store, esperando)
        if decisao is not None:
            return decisao

    # Não sabemos o que é — mas sabemos que merece resposta. Cair em
    # CONSULTIVA manda para quem responde em texto, em vez de para o silêncio.
    if esperando == 'observacao':
        return Decisao(intencao=Intencao.OBSERVACAO, texto=texto)
    return Decisao(intencao=Intencao.CONSULTIVA, texto=texto)


def _produtos(store, texto: str) -> list:
    if store is None:
        return []
    from apps.stores.services.busca_de_produto import candidatos_de_produto

    return candidatos_de_produto(store, texto)


def _perguntar_ao_modelo(classificador, texto, store, esperando) -> Optional[Decisao]:
    """Chama o classificador injetado e valida o que voltou.

    Devolve None quando o modelo falha ou responde algo que não é uma Decisao —
    o chamador então segue pelo caminho determinístico. Validar aqui, e não
    confiar no formato, é o que mantém a promessa de nunca calar.
    """
    try:
        resposta = classificador(texto, store=store, esperando=esperando)
    except Exception as exc:
        logger.warning('[triagem] classificador falhou, seguindo sem ele: %s', exc)
        return None

    if not isinstance(resposta, Decisao):
        logger.warning('[triagem] classificador devolveu %s, ignorando', type(resposta))
        return None

    resposta.origem = 'llm'
    return resposta
