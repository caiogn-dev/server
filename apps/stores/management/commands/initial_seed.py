"""
Management command to seed database ONLY if empty.

Usage:
    python manage.py initial_seed
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from apps.stores.models import Store


class Command(BaseCommand):
    help = 'Seed database with initial data if it is empty.'

    def handle(self, *args, **options):
        total_stores = Store.objects.count()

        if total_stores == 0:
            self.stdout.write(self.style.WARNING('BD vazio. Rodando seed inicial...'))
            try:
                call_command('populate_ce_saladas_menu')
                call_command('populate_pastita_menu')
                call_command('populate_kero_kero_menu')
                call_command('populate_delivery_zones')
                self.stdout.write(self.style.SUCCESS('✅ Seed inicial completado'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Erro no seed: {str(e)}'))
                raise
        else:
            self.stdout.write(f'✅ BD já tem {total_stores} lojas. Pulando seed.')
