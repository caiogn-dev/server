"""O lembrete de PIX do site precisa estar agendado com o NOME CERTO.

A entrada antiga apontava para `apps.whatsapp.tasks.check_pending_payments` —
nome que nenhuma tarefa registra. Ficou anos no agendador sem nunca rodar e
ninguém percebeu, porque tarefa inexistente falha calada. O dono ligou o
lembrete em 21/09; este teste garante que ele aponta para uma tarefa que
existe de verdade.
"""
import pytest

from config.celery import app as celery_app

NOME = 'apps.whatsapp.tasks.automation_tasks.check_pending_payments'


def test_o_lembrete_de_pix_esta_agendado():
    tarefas = {e['task'] for e in celery_app.conf.beat_schedule.values()}

    assert NOME in tarefas


def test_toda_tarefa_agendada_existe_de_verdade():
    """Agendar nome que ninguém registra = tarefa que nunca roda, em silêncio."""
    import apps  # noqa: F401  — garante o autodiscover

    celery_app.loader.import_default_modules()
    registradas = set(celery_app.tasks.keys())

    agendadas = {e['task'] for e in celery_app.conf.beat_schedule.values()}
    fantasmas = sorted(t for t in agendadas if t not in registradas)

    assert fantasmas == [], f'agendadas e inexistentes: {fantasmas}'
