"""A suíte NUNCA pode falar com o Redis de produção.

Em Celery 5, `app.conf.broker_url` é uma *property* que consulta
`os.environ['CELERY_BROKER_URL']` a cada leitura, ANTES de olhar o settings. O
ambiente do processo passa por cima do Django, e escrever
`app.conf.broker_url = ...` não vence — a property lê o env de novo.

E o ambiente aqui é o de produção: `pastita_backend:latest` nasce de
`docker commit pastita_web`, então carrega o env da loja viva assado dentro da
imagem. Medido em 14/ago: a suíte tentava alcançar `redis://redis:6379`, levava
20 retries de 1s e queimava 129s POR TESTE antes de falhar.

`config/settings/test.py` resolve removendo a variável do ambiente. Estes
testes são a trava para isso não voltar em silêncio — e o sintoma de volta
seria lentidão, não erro, que é o jeito mais fácil de não perceber.
"""
import os

import pytest


def test_o_env_de_producao_nao_sobrevive_ao_settings_de_teste():
    assert os.environ.get('CELERY_BROKER_URL') is None
    assert os.environ.get('CELERY_RESULT_BACKEND') is None


def test_o_broker_efetivo_nao_e_o_de_producao():
    """`redis:6379` é o host do compose de produção."""
    from config.celery import app

    assert 'redis://redis:' not in str(app.conf.broker_url)
    assert 'redis://redis:' not in str(app.conf.result_backend)


def test_o_broker_efetivo_segue_o_settings():
    from django.conf import settings

    from config.celery import app

    assert app.conf.broker_url == settings.CELERY_BROKER_URL
    assert app.conf.result_backend == settings.CELERY_RESULT_BACKEND


@pytest.mark.django_db
def test_redis_url_tambem_nao_aponta_para_producao():
    """`create_redis_client` lê `settings.REDIS_URL` direto, sem passar por CACHES."""
    from django.conf import settings

    assert 'redis://redis:' not in str(settings.REDIS_URL)


def test_shared_task_pertence_a_NOSSA_app_e_nao_a_uma_default():
    """A causa raiz, travada.

    `config/__init__.py` esteve VAZIO até 14/ago/2026. Sem
    `from .celery import app as celery_app` ali, `@shared_task` se liga a uma
    app default do Celery em vez da nossa — e aí `task_routes`, broker e
    `task_always_eager` do settings simplesmente não se aplicam.

    Verificado em produção naquele dia: no processo web, `app.main` era
    'default' e `task_routes` estava vazio. Tarefas enfileiradas por signals e
    views iam para a fila `celery` em vez de `whatsapp`/`agents`/etc. Não
    quebrava porque o worker sobe com `-Q celery,...,default` e consome todas —
    quebra no dia em que houver um worker por fila.
    """
    from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
    from config.celery import app

    assert notify_order_status_change.app is app, (
        'a task caiu numa app default — config/__init__.py não está importando '
        'a app do Celery'
    )
    assert app.conf.task_routes, 'task_routes vazio: as filas nomeadas não valem'


def test_o_modo_eager_do_settings_realmente_alcanca_as_tasks():
    """Consequência direta do anterior — e o que fazia a suíte falar com broker real."""
    from apps.whatsapp.tasks.automation_tasks import notify_order_status_change

    assert notify_order_status_change.app.conf.task_always_eager is True
