"""Redis fora do ar não pode calar a loja.

`acquire_lock` promete no próprio docstring "No Redis, no lock" — degradar sem
travar. Só que `redis.from_url()` é PREGUIÇOSO: ele não conecta, apenas monta o
cliente. O `try/except` em volta dele nunca via erro nenhum, e a falha real
aparecia no `client.set()` seguinte, subindo pela pilha e derrubando
`process_webhook_event`.

Consequência: um soluço do Redis não deixava o lock "aberto" — deixava **toda
mensagem recebida sem processamento**. O cliente escreve e ninguém responde,
que é o desfecho que este projeto passou o dia 10/ago combatendo.

O trade-off é explícito: sem Redis o lock deixa passar, e duas execuções
simultâneas do mesmo evento viram possibilidade. Processar duas vezes é ruim;
não processar é pior — e a idempotência do WebhookEvent ainda protege.
"""
from unittest.mock import MagicMock, patch

import pytest
import redis

from apps.whatsapp.tasks import acquire_lock, release_lock


class TestLockComRedisSaudavel:
    def test_pega_o_lock_quando_esta_livre(self):
        cliente = MagicMock()
        cliente.set.return_value = True
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=cliente):
            assert acquire_lock('x') is True
        cliente.set.assert_called_once()

    def test_nao_pega_quando_outro_worker_ja_tem(self):
        cliente = MagicMock()
        cliente.set.return_value = None
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=cliente):
            assert not acquire_lock('x')


class TestRedisForaDoAr:
    """O caso que derrubava tudo."""

    @pytest.mark.parametrize('erro', [
        redis.ConnectionError('connection refused'),
        redis.TimeoutError('timed out'),
        redis.RedisError('qualquer coisa'),
    ])
    def test_falha_ao_pegar_o_lock_deixa_passar(self, erro):
        cliente = MagicMock()
        cliente.set.side_effect = erro
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=cliente):
            assert acquire_lock('x') is True, 'sem Redis o lock tem que liberar, não explodir'

    def test_falha_ao_soltar_o_lock_nao_levanta(self):
        """O release roda no finally: se ele levanta, mascara o erro original."""
        cliente = MagicMock()
        cliente.delete.side_effect = redis.ConnectionError('connection refused')
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=cliente):
            release_lock('x')  # não pode levantar

    def test_sem_cliente_nenhum_continua_liberando(self):
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=None):
            assert acquire_lock('x') is True
            release_lock('x')

    def test_erro_inesperado_tambem_libera(self):
        """Guarda larga de propósito: a promessa é 'nunca calar a loja'."""
        cliente = MagicMock()
        cliente.set.side_effect = OSError('socket morreu')
        with patch('apps.whatsapp.tasks.get_redis_client', return_value=cliente):
            assert acquire_lock('x') is True
