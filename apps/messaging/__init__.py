# Messaging Module
"""
Módulo de integração com Messenger Platform.

Funcionalidades:
- Messenger Platform (webhooks, profile)
- Messenger Advanced (broadcast, sponsored messages, extensions)
- Handover Protocol
- One-Time Notification

Estrutura:
- models.py: Modelos de dados
- services/: Serviços de integração com APIs
- api/: Views e serializers REST
- tasks.py: Tarefas Celery
- admin.py: Configuração do Django Admin
"""

default_app_config = 'apps.messaging.apps.MessagingConfig'
