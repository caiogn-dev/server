"""Toda tarefa agendada no beat precisa existir no worker.

19/09: duas entradas do beat apontavam para nomes que nenhuma tarefa usa —
`apps.automation.tasks.check_abandoned_carts` (a registrada chama
`...check_abandoned_sessions`) e `apps.whatsapp.tasks.check_pending_payments`
(a registrada é `...automation_tasks.check_pending_payments`). O beat
disparou 28.011 e 14.008 vezes sem executar código nenhum, e um comentário
ainda chamava a primeira de "fonte única". Nada acusava.
"""
from config.celery import app


def test_toda_tarefa_do_beat_esta_registrada():
    app.loader.import_default_modules()
    registradas = set(app.tasks.keys())
    faltando = {
        nome: entrada['task']
        for nome, entrada in (app.conf.beat_schedule or {}).items()
        if entrada['task'] not in registradas
    }
    assert faltando == {}, f'beat agenda tarefa que não existe: {faltando}'


def test_migracao_apaga_so_as_entradas_fantasmas(db):
    from importlib import import_module
    from django.apps import apps as django_apps
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    migracao = import_module('apps.stores.migrations.0084_beat_sem_tarefa_fantasma')
    cada_5 = IntervalSchedule.objects.create(every=300, period=IntervalSchedule.SECONDS)
    for nome, tarefa in [
        ('fantasma-1', 'apps.automation.tasks.check_abandoned_carts'),
        ('fantasma-2', 'apps.whatsapp.tasks.check_pending_payments'),
        ('viva', 'apps.whatsapp.tasks.check_abandoned_whatsapp_sessions'),
    ]:
        PeriodicTask.objects.create(name=nome, task=tarefa, interval=cada_5)

    migracao.apagar(django_apps, None)

    assert list(PeriodicTask.objects.filter(name__in=['fantasma-1', 'fantasma-2', 'viva'])
                .values_list('name', flat=True)) == ['viva']
