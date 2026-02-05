"""
Management command to fix media URLs in messages.
Converts backend.pastita.com.br URLs to S3 URLs.
"""
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from apps.whatsapp.models import Message


class Command(BaseCommand):
    help = 'Fix media URLs in messages to use correct S3 URLs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find messages with backend.pastita.com.br URLs
        messages = Message.objects.filter(
            media_url__contains='backend.pastita.com.br'
        )
        
        self.stdout.write(f"Found {messages.count()} messages with old URLs")
        
        fixed_count = 0
        error_count = 0
        
        for msg in messages:
            old_url = msg.media_url
            # Extract the path after the domain
            # e.g., https://backend.pastita.com.br/whatsapp/xxx/yyy.jpg -> whatsapp/xxx/yyy.jpg
            try:
                path = old_url.replace('https://backend.pastita.com.br/', '')
                
                # Generate new URL using storage
                new_url = default_storage.url(path)
                
                if dry_run:
                    self.stdout.write(f"  Would fix: {old_url}")
                    self.stdout.write(f"         -> {new_url}")
                else:
                    msg.media_url = new_url
                    msg.save(update_fields=['media_url'])
                    self.stdout.write(f"  Fixed: {msg.id}")
                
                fixed_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error fixing {msg.id}: {e}"))
                error_count += 1
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"\nDry run: {fixed_count} would be fixed, {error_count} errors"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nFixed {fixed_count} messages, {error_count} errors"))
