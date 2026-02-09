"""
Users app - Unified user management

Este app gerencia usuários unificados que podem acessar:
- Site (pastita-3d)
- WhatsApp
- E ter um perfil unificado

NÃO ALTERA modelos existentes, apenas adiciona relações.
"""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    verbose_name = 'Usuários'
    
    def ready(self):
        """Import signals quando o app estiver pronto"""
        import apps.users.signals  # noqa
