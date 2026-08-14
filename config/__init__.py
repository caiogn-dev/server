"""Torna a app do Celery a app corrente de TODO processo Django.

Sem isto — e este arquivo esteve vazio até 14/ago/2026 — `@shared_task` se liga
a uma app default do Celery, e não à nossa. Consequências, todas silenciosas:

- `task_routes` fica VAZIO no processo web, então tarefas enfileiradas por
  signals e views vão para a fila `celery` em vez de `whatsapp` / `agents` /
  `automation` / `campaigns`. Hoje não quebra nada porque o worker sobe com
  `-Q celery,...,default` e consome todas. Quebra no dia em que houver um
  worker por fila — que é exatamente o motivo de o `task_routes` existir.
- O broker só está certo por acidente: `conf.broker_url` é uma property que lê
  `os.environ['CELERY_BROKER_URL']` a cada acesso, e o container tem a variável.
  Tirar a variável do compose apontaria a app default para `amqp://localhost`.
- Na suíte, `CELERY_TASK_ALWAYS_EAGER` não valia para essas tasks: elas
  pertenciam a outra app. Foi assim que testes de checkout tentaram falar com
  um broker de verdade.

O worker escapava porque sobe com `-A config.celery`, que importa e fixa a app.
Só o processo web ficava de fora.

Ref: docs oficiais do Celery, "First steps with Django".
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
