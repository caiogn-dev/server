"""
Setup inicial para Celery Beat - Criar tarefas periódicas.
Executar uma vez: python manage.py shell < setup_celery_beat.py
"""
from django_celery_beat.models import PeriodicTask, IntervalSchedule

# Criar schedule de 1 minuto
schedule, _ = IntervalSchedule.objects.get_or_create(
    every=1,
    period=IntervalSchedule.MINUTES
)

# Tarefa: Verificar campanhas agendadas
PeriodicTask.objects.get_or_create(
    name='Schedule Campaigns',
    defaults={
        'interval': schedule,
        'task': 'apps.marketing_v2.tasks.schedule_campaigns',
        'enabled': True
    }
)

# Tarefa: Processar carrinhos abandonados
PeriodicTask.objects.get_or_create(
    name='Process Abandoned Carts',
    defaults={
        'interval': schedule,
        'task': 'apps.marketing_v2.tasks.process_abandoned_carts',
        'enabled': True
    }
)

# Tarefa: Atualizar métricas do dashboard
PeriodicTask.objects.get_or_create(
    name='Update Dashboard Metrics',
    defaults={
        'interval': schedule,
        'task': 'apps.commerce.tasks.update_dashboard_metrics',
        'enabled': True
    }
)

print("✅ Tarefas periódicas configuradas!")
