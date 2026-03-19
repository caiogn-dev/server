# Messaging Module
"""
Módulo de integração com Messenger Platform (Facebook Messenger).

NOTA IMPORTANTE: Apesar do nome 'messaging', este app gerencia
exclusivamente a integração com o Facebook Messenger Platform.
Não existe um app separado 'apps.messenger' — este IS o app do Messenger.

Funcionalidades:
- Messenger Platform (webhooks, profile, conversations)
- Messenger Advanced (broadcast, sponsored messages, extensions)
- Configuração de perfil de página (greeting, menus, ice breakers)

Estrutura:
- models.py: Modelos de dados (MessengerAccount, MessengerConversation, etc.)
- services/: Serviços de integração com a Graph API do Facebook
- api/: Views e serializers REST
- tasks.py: Tarefas Celery
- admin.py: Configuração do Django Admin
- dispatcher.py: INCOMPLETO — camada genérica multi-canal nunca finalizada
                 (ver TODOs em dispatcher.py e models.py)
"""

default_app_config = 'apps.messaging.apps.MessagingConfig'
