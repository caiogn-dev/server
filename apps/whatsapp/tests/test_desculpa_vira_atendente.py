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


def test_reconhece_TODAS_as_variantes_do_pedido_de_desculpas():
    """Havia quatro textos de desculpa espalhados pelo código.

    Achados em 22/09: `avisos.MENSAGEM_DE_ERRO_DO_LLM` ("probleminha aqui"),
    `langgraph_service` ("tive um problema. Pode repetir?") e, em produção,
    mensagens antigas com "problema ao processar sua mensagem". Reconhecer só
    uma delas deixa as outras passarem como se fossem resposta — e o cliente
    volta a receber desculpa em vez de atendente.
    """
    from apps.whatsapp.tasks import resposta_e_falha_da_ia

    for texto in (
        'Desculpa, tive um probleminha aqui. Pode repetir?',
        'Desculpa, tive um problema. Pode repetir?',
        'Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?',
    ):
        assert resposta_e_falha_da_ia(texto) is True, texto


def test_texto_que_so_fala_de_problema_nao_e_falha_da_ia():
    """"Tive um problema pra gerar o link" é resposta de verdade, do handler
    de pagamento: diz o que houve e o que fazer. Não pode virar atendente."""
    from apps.whatsapp.tasks import resposta_e_falha_da_ia

    assert resposta_e_falha_da_ia(
        'Tive um problema pra gerar o link agora. 😕 Pode pagar na entrega?'
    ) is False


# ---------------------------------------------------------------------------
# 22/09, segunda rodada: o guarda estava no lugar errado.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_send_agent_response_NUNCA_entrega_a_desculpa():
    """O guarda mora no gargalo, não em cada caminho que chama o agente.

    O fix da manhã de 22/09 protegeu `process_message_with_agent` — e o cliente
    continuou recebendo a desculpa. Medido na conversa da Sarah Lorrany:

        14:48:49  outbound  "Desculpa, tive um probleminha aqui..."
        14:49:10  outbound  "Desculpa, tive um probleminha aqui..."
        14:50:57  outbound  "Desculpa, tive um probleminha aqui..."

    Porque quem enviou não foi aquela tarefa: foi o "Caminho B" de
    `_dispatch_orchestrator_response`, que enfileirava
    `orchestrator_response.content` sem olhar o que era. O caminho ATRASADO,
    logo acima dele, já tinha exatamente esta checagem — o normal não.

    Guardar caminho por caminho é uma corrida que se perde: eram três, e o
    terceiro não existia quando os dois primeiros foram escritos.
    `send_agent_response` é por onde TODA resposta automática sai, então é
    onde a regra tem que morar.
    """
    from apps.whatsapp import tasks

    with patch.object(tasks, 'MessageService', create=True) as _ms, \
         patch('apps.whatsapp.services.MessageService') as servico, \
         patch.object(tasks, '_passar_para_atendente_por_falha_da_ia') as escalar:
        tasks.send_agent_response(
            account_id='00000000-0000-0000-0000-000000000000',
            to='5563999999999',
            response_text=MENSAGEM_DE_ERRO_DO_LLM,
            reply_to=None,
            response_source='unified_agent',
        )

    assert not servico.return_value.send_text_message.called, (
        'a desculpa foi entregue ao cliente'
    )


@pytest.mark.django_db
def test_send_agent_response_entrega_resposta_de_verdade():
    """O par do teste acima: o guarda não pode calar o bot que funciona."""
    from apps.whatsapp import tasks

    with patch('apps.whatsapp.services.MessageService') as servico:
        tasks.send_agent_response(
            account_id='00000000-0000-0000-0000-000000000000',
            to='5563999999999',
            response_text='Atendemos domingo das 11h às 15h 😊',
            reply_to=None,
            response_source='unified_agent',
        )

    assert servico.return_value.send_text_message.called, (
        'resposta boa foi engolida pelo guarda'
    )
