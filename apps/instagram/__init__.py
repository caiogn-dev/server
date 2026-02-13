# Instagram Module
"""
Módulo de integração com Instagram via Graph API.

Funcionalidades:
- Graph API (Posts, Stories, Reels, agendamento)
- Shopping (product tags, catalog)
- Live (streaming, comentários)
- Direct Advanced (reactions, replies, unsend, voice)

Estrutura:
- models.py: Modelos de dados
- services/: Serviços de integração com APIs
- api/: Views e serializers REST
- tasks.py: Tarefas Celery
- admin.py: Configuração do Django Admin
"""

default_app_config = 'apps.instagram.apps.InstagramConfig'
