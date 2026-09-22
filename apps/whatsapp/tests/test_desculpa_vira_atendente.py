"""A desculpa do LLM não é resposta — é falha, e falha vai para o atendente.

Decisão do dono em 17/set, depois de o Francisco receber dois "desculpe" em 4
minutos: quando a IA não responde, a conversa passa para uma pessoa e o painel
é avisado. Isso já existia — só que **só disparava quando a chamada levantava
exceção**.

E o grafo não levanta: ele captura o erro por dentro e devolve
`MENSAGEM_DE_ERRO_DO_LLM` como se fosse uma resposta normal
(`apps/agents/graph/nodes.py`). Então o caminho de escalonamento nunca era
alcançado e o cliente recebia a desculpa.

Medido em 21/09: 60 desculpas em 30 dias, todas pelo caminho do LLM, com a
chave da NVIDIA respondendo **403 Forbidden**. Perguntas normais ("Vocês
atendem no domingo??", "Aonde vcs ficam") viraram pedido de desculpas em vez
de virar atendimento.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.agents.avisos import MENSAGEM_DE_ERRO_DO_LLM


def test_a_desculpa_e_reconhecida_como_falha():
    from apps.whatsapp.tasks import resposta_e_falha_da_ia

    assert resposta_e_falha_da_ia(MENSAGEM_DE_ERRO_DO_LLM) is True
    assert resposta_e_falha_da_ia('  ' + MENSAGEM_DE_ERRO_DO_LLM + ' ') is True


def test_resposta_de_verdade_nao_e_falha():
    from apps.whatsapp.tasks import resposta_e_falha_da_ia

    assert resposta_e_falha_da_ia('Oi! Atendemos domingo das 11h às 15h 😊') is False
    assert resposta_e_falha_da_ia('') is False
    assert resposta_e_falha_da_ia(None) is False
