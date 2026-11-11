"""Bot mandou lixo para cliente da Cê Saladas em 11/nov/2026.

O `nemotron-3-ultra` na NVIDIA NIM passou a devolver, para o MESMO pedido,
ora texto bom, ora vazio, ora sopa de tokens ("那些Re)))))))…"). Cinco
mensagens assim saíram para clientes num dia — e cada uma foi gravada no
histórico do Redis, envenenando os turnos seguintes da mesma conversa.

O caminho de produção (`LangGraphService`) não passava pela trava de
`texto_para_o_cliente`, que só o loop antigo (`LangchainService`) usava.

Agora: lixo é detectado, refeito uma vez e, se continuar lixo, não sai e não
entra no histórico — quem chama recebe resposta vazia e cai no fallback.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from apps.agents.services.resposta_do_modelo import (
    RespostaDoModeloInvalida,
    texto_para_o_cliente,
)

# Textos REAIS enviados em 11/nov/2026 (Cê Saladas) + um da medição direta.
LIXO_REAL = [
    '0 星-0--',
    '那些s)�(',
    ".11Ref)IC)Gener))..Ch))�)�-Re)那些Re) (E Service),Re)0�...、1,、,,.,)Re)、Ré),),�Re)_interval)",
    '(ianss(r))�(�)))S)))2)22)) (2{(22))(()((((-(((.s)())).F))))))))))))))))))))))',
    'mui──\n\n Xôसिंह�underlineCharactersyyy.User��ctoj',
]

CODIGO_CRU = [
    '<tool_call>{"name": "consultar_cardapio", "arguments": {}}</tool_call>',
    '```python\nprint(cardapio)\n```',
    '{"name": "consultar_cardapio", "parameters": {"categoria": "saladas"}}',
]

BOAS = [
    'Oi! Sim, entregamos no Plano Diretor Sul 😊\n\nNosso horário é de *11h às 14h30*.',
    'Temos Caesar (R$ 32,90) e Mediterrânea (R$ 34,90). Quer que eu monte o pedido?',
    'Perfeito! 2x Caesar = R$ 65,80 + entrega R$ 6,00. Pix ou cartão na entrega?',
    'Pedido #CE-2611 confirmado ✅ (sai em ~40 min)',
    'Ok :)',
    'Nosso cardápio: https://cardapidex.com.br/ce-saladas',
]


@pytest.mark.parametrize('texto', LIXO_REAL + CODIGO_CRU)
def test_lixo_e_codigo_cru_sao_barrados(texto):
    with pytest.raises(RespostaDoModeloInvalida) as erro:
        texto_para_o_cliente(texto, 'stop')
    assert erro.value.motivo == 'texto_degenerado'


@pytest.mark.parametrize('texto', BOAS)
def test_respostas_normais_passam(texto):
    assert texto_para_o_cliente(texto, 'stop') == texto.strip()


# ── LangGraphService: o caminho de produção ──────────────────────────────────

def _servico(respostas):
    """LangGraphService com grafo falso que devolve `respostas` em sequência."""
    from apps.agents.services.langgraph_service import LangGraphService

    svc = LangGraphService.__new__(LangGraphService)
    svc.agent = MagicMock(model_name='nvidia/nemotron-3-ultra-550b-a55b', max_context_messages=10)
    memoria = MagicMock()
    memoria.messages = []
    svc._lc = MagicMock()
    svc._lc._get_memory.return_value = memoria
    grafo = MagicMock()
    grafo.invoke.side_effect = [{'response': r} for r in respostas]
    svc._graph = grafo
    svc._get_graph = lambda: grafo
    return svc, grafo, memoria


def test_lixo_e_refeito_e_so_a_boa_vai_para_o_historico():
    svc, grafo, memoria = _servico([LIXO_REAL[2], BOAS[0]])
    out = svc.process_message('oi', session_id='s1')
    assert out['response'] == BOAS[0]
    assert grafo.invoke.call_count == 2
    memoria.add_ai_message.assert_called_once_with(BOAS[0])


def test_vazio_tambem_e_refeito():
    svc, grafo, _ = _servico(['', BOAS[1]])
    assert svc.process_message('oi', session_id='s1')['response'] == BOAS[1]
    assert grafo.invoke.call_count == 2


def test_lixo_duas_vezes_nao_sai_nem_entra_no_historico():
    svc, grafo, memoria = _servico([LIXO_REAL[0], LIXO_REAL[3]])
    out = svc.process_message('oi', session_id='s1')
    assert out['response'] == ''
    memoria.add_ai_message.assert_not_called()
    memoria.add_user_message.assert_not_called()


def test_resposta_boa_nao_refaz():
    svc, grafo, memoria = _servico([BOAS[2]])
    assert svc.process_message('oi', session_id='s1')['response'] == BOAS[2]
    assert grafo.invoke.call_count == 1
    memoria.add_ai_message.assert_called_once_with(BOAS[2])


def test_ultimo_turno_do_historico_com_lixo_e_ignorado():
    """Conversas de 11/nov já têm lixo gravado no Redis: não pode voltar ao modelo."""
    svc, grafo, memoria = _servico([BOAS[0]])
    memoria.messages = [AIMessage(content=LIXO_REAL[3]), AIMessage(content=BOAS[1])]
    svc.process_message('oi', session_id='s1')
    enviadas = grafo.invoke.call_args[0][0]['messages']
    conteudos = [m.content for m in enviadas]
    assert LIXO_REAL[3] not in conteudos
    assert BOAS[1] in conteudos


def test_nao_refaz_quando_a_rodada_ja_chamou_ferramenta():
    """Refazer repetiria criar_pedido/gerar_pix: pedido em dobro é pior que fallback."""
    svc, grafo, memoria = _servico([])
    grafo.invoke.side_effect = [{'response': LIXO_REAL[2], 'tool_call_count': 1}]
    out = svc.process_message('quero 2 caesar', session_id='s1')
    assert out['response'] == ''
    assert grafo.invoke.call_count == 1
    memoria.add_ai_message.assert_not_called()
