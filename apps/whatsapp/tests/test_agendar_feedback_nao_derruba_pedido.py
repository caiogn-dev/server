"""Agendar o convite de avaliação não pode derrubar o salvamento do pedido.

`schedule_feedback_request` usava `current_app.send_task(...)`, e `send_task`
NÃO respeita `task_always_eager` — ele fala com o broker de verdade. Duas
consequências:

1. **Produção**: a chamada nasce de um signal em `post_save` de StoreOrder, via
   `transaction.on_commit`. Um soluço do Redis levantava DENTRO do commit e
   derrubava a atualização de status do pedido. É a mesma classe do bug do
   `acquire_lock` corrigido hoje cedo: infraestrutura auxiliar derrubando o
   caminho principal.

2. **Teste**: a suíte tentava alcançar `redis://redis:6379` — o Redis da loja
   viva — e falhava com `socket.gaierror -3`, parecendo problema de ambiente
   sem conserto.

Contrato: agendar é acessório. Falhou, registra e segue.
"""
from unittest.mock import patch

import pytest


@pytest.mark.django_db
class TestAgendarFeedback:
    def test_usa_apply_async_e_respeita_o_modo_eager(self):
        """`send_task` ignora ALWAYS_EAGER; `apply_async` da própria task não."""
        from apps.whatsapp.tasks import automation_tasks

        with patch.object(automation_tasks.request_feedback, 'apply_async') as agendou:
            automation_tasks.schedule_feedback_request('abc-123')

        agendou.assert_called_once()
        assert agendou.call_args.kwargs['countdown'] == 30 * 60

    def test_broker_fora_do_ar_nao_levanta(self):
        """Roda dentro do commit do pedido — levantar aqui desfaz a venda."""
        from apps.whatsapp.tasks import automation_tasks

        with patch.object(
            automation_tasks.request_feedback, 'apply_async',
            side_effect=ConnectionError('redis fora'),
        ):
            automation_tasks.schedule_feedback_request('abc-123')  # não pode levantar
