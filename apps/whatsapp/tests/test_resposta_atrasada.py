"""
Resposta pronta depois do timeout deve ser entregue, não jogada fora.

Produção 09/ago (msg be0c7818): o orquestrador levou 78,7s, o join desistiu aos
90s e a resposta — já calculada — foi descartada. O fallback então reprocessou
a mensagem inteira pelo caminho legado. O cliente esperou ~3 minutos por uma
resposta que existia aos 78 segundos.

Regra: chegar tarde é ruim, jogar fora e refazer é pior. Mas entregar duas
vezes é inaceitável, então a thread só entrega se o fallback ainda não entregou.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services import ResponseSource, UnifiedResponse
from apps.whatsapp.services.webhook_service import WebhookService


@pytest.fixture
def servico():
    return WebhookService()


def _mensagem(processed=False):
    msg = MagicMock()
    msg.id = 'msg-1'
    msg.from_number = '5563999999999'
    msg.whatsapp_message_id = 'wamid.1'
    msg.processed_by_agent = processed

    def _refresh(fields=None):
        return None

    msg.refresh_from_db.side_effect = _refresh
    return msg


def _evento():
    ev = MagicMock()
    ev.account.id = 'acc-1'
    return ev


def test_entrega_a_resposta_que_chegou_tarde(servico):
    msg = _mensagem(processed=False)
    resposta = UnifiedResponse(content='Oi! O molho vai à parte.', source=ResponseSource.LLM)

    with patch('apps.whatsapp.tasks.send_agent_response') as envio, \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        servico._enviar_resposta_atrasada(_evento(), msg, resposta)

    envio.delay.assert_called_once()
    assert 'molho vai à parte' in envio.delay.call_args[0][2]


def test_nao_duplica_quando_o_fallback_ja_respondeu(servico):
    """Sem esta guarda o cliente recebe a mesma pergunta respondida duas vezes."""
    msg = _mensagem(processed=True)
    resposta = UnifiedResponse(content='Oi! O molho vai à parte.', source=ResponseSource.LLM)

    with patch('apps.whatsapp.tasks.send_agent_response') as envio:
        servico._enviar_resposta_atrasada(_evento(), msg, resposta)

    envio.delay.assert_not_called()


def test_ignora_resposta_vazia(servico):
    msg = _mensagem(processed=False)

    with patch('apps.whatsapp.tasks.send_agent_response') as envio:
        servico._enviar_resposta_atrasada(_evento(), msg, UnifiedResponse(content='   ', source=ResponseSource.LLM))

    envio.delay.assert_not_called()


def test_falha_no_envio_nao_derruba_a_thread(servico):
    """A entrega atrasada roda numa thread daemon — exceção ali some sem rastro."""
    msg = _mensagem(processed=False)

    with patch('apps.whatsapp.tasks.send_agent_response') as envio, \
         patch.object(WebhookService, '_mark_processed_by_agent'):
        envio.delay.side_effect = RuntimeError('broker fora do ar')
        servico._enviar_resposta_atrasada(_evento(), msg, UnifiedResponse(content='oi', source=ResponseSource.LLM))
    # não levantou


def test_sinaliza_desistencia_so_depois_de_medir_se_a_thread_vive():
    """Ordem importa: set() antes do is_alive() permitiria entrega dupla.

    Se a thread terminasse entre o set() e o is_alive(), ela entregaria por ser
    "atrasada" e o caminho principal entregaria por não ter dado timeout.
    """
    import inspect

    fonte = inspect.getsource(WebhookService._run_orchestrator_with_timeout)
    pos_is_alive = fonte.index('timed_out = _thread.is_alive()')
    pos_set = fonte.index('_desistiu.set()')

    assert pos_is_alive < pos_set, 'is_alive() tem que ser medido antes de sinalizar'
