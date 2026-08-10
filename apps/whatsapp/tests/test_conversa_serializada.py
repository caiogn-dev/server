"""
Duas mensagens do mesmo cliente não podem montar o carrinho em paralelo.

Conversa de 09/ago, 20:20:

    20:20:37  CLIENTE  Sim monta
    20:20:49  CLIENTE  Repetir
    20:20:49  BOT      Prontinho! Montei igualzinho ao seu último pedido: ...
    20:20:58  BOT      Prontinho, seu pedido está montado! ...
    20:21:21  CLIENTE  E cadê o de tomate seco e 4 queijos?
    20:21:28  BOT      Ah, entendi! O carrinho acabou duplicando os itens —
                       2x Rondelli de Frango, 2x Rondelli 4 Queijos ...

Cada mensagem rodou numa thread daemon própria, as duas leram o mesmo carrinho
do Redis e as duas escreveram por cima. `acquire_lock` já existia em
whatsapp/tasks, mas é por message_id: protege contra processar a MESMA mensagem
duas vezes, não contra duas mensagens diferentes do mesmo cliente.

A trava é por CONVERSA: a segunda mensagem espera a primeira terminar e enxerga
o carrinho já montado.
"""
from unittest.mock import MagicMock, patch

from apps.whatsapp.services.webhook_service import WebhookService


def _servico():
    return WebhookService()


def test_gera_chave_de_lock_por_conversa():
    svc = _servico()
    msg = MagicMock()
    msg.conversation.id = 'conv-123'

    assert svc._chave_de_lock_da_conversa(msg) == 'orquestrador:conversa:conv-123'


def test_sem_conversa_cai_no_telefone():
    """Mensagem sem conversa ainda precisa serializar por cliente."""
    svc = _servico()
    msg = MagicMock()
    msg.conversation = None
    msg.from_number = '5563999999999'

    assert svc._chave_de_lock_da_conversa(msg) == 'orquestrador:telefone:5563999999999'


def test_segunda_mensagem_espera_a_primeira():
    svc = _servico()
    msg = MagicMock()
    msg.conversation.id = 'conv-123'

    with patch('apps.whatsapp.services.webhook_service.acquire_lock') as trava:
        trava.return_value = True
        with svc._conversa_serializada(msg) as obteve:
            assert obteve is True
        trava.assert_called_once()


def test_processa_mesmo_sem_conseguir_a_trava():
    """Perder a trava não pode virar mensagem sem resposta.

    Melhor arriscar uma duplicata rara do que deixar o cliente falando sozinho —
    MESSAGE DROPPED é o pior desfecho possível do pipeline.
    """
    svc = _servico()
    msg = MagicMock()
    msg.conversation.id = 'conv-123'

    with patch('apps.whatsapp.services.webhook_service.acquire_lock', return_value=False):
        with svc._conversa_serializada(msg) as obteve:
            assert obteve is False


def test_libera_a_trava_mesmo_com_excecao():
    svc = _servico()
    msg = MagicMock()
    msg.conversation.id = 'conv-123'

    with patch('apps.whatsapp.services.webhook_service.acquire_lock', return_value=True), \
         patch('apps.whatsapp.services.webhook_service.release_lock') as solta:
        try:
            with svc._conversa_serializada(msg):
                raise RuntimeError('estourou no meio')
        except RuntimeError:
            pass

    solta.assert_called_once_with('orquestrador:conversa:conv-123')
