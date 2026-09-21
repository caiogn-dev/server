"""O lembrete de PIX do site está agendado — e com o nome certo.

A entrada antiga apontava para `apps.whatsapp.tasks.check_pending_payments`,
nome que nenhuma tarefa registra; ficou no agendador sem nunca rodar, porque
tarefa inexistente falha calada. Que TODA entrada aponte para tarefa real é
garantido por `apps/core/tests/test_beat_so_agenda_tarefa_que_existe.py`;
aqui a garantia é só que este lembrete continua agendado.
"""
from config.celery import app as celery_app

NOME = 'apps.whatsapp.tasks.automation_tasks.check_pending_payments'


def test_o_lembrete_de_pix_esta_agendado():
    tarefas = {e['task'] for e in celery_app.conf.beat_schedule.values()}

    assert NOME in tarefas
