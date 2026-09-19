"""Apaga do beat duas entradas que apontavam para tarefas que não existem.

O `DatabaseScheduler` copia o `beat_schedule` do config/celery.py para o banco
ao subir e nunca apaga o que saiu de lá. Estas duas nunca executaram código
(nome sem tarefa registrada): 28.011 e 14.008 disparos vazios até 19/09/2026.
"""
from django.db import migrations

FANTASMAS = (
    'apps.automation.tasks.check_abandoned_carts',
    'apps.whatsapp.tasks.check_pending_payments',
)


def apagar(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(task__in=FANTASMAS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0083_dominio_proprio_validado'),
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]
    operations = [migrations.RunPython(apagar, migrations.RunPython.noop)]
