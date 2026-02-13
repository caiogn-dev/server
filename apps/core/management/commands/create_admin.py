"""
Management command to create admin user from environment variables.
"""
import os
import secrets
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create admin user from environment variables'

    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        
        # SECURITY: Never use hardcoded password - require env var or generate secure random
        password = os.environ.get('ADMIN_PASSWORD')
        generated = False
        
        if not password:
            password = secrets.token_urlsafe(16)
            generated = True

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists'))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        self.stdout.write(self.style.SUCCESS(f'Admin user "{username}" created successfully!'))
        
        if generated:
            self.stdout.write(self.style.WARNING(f'Generated password (SAVE THIS!): {password}'))
            self.stdout.write(self.style.WARNING('Set ADMIN_PASSWORD env var to use your own password.'))
