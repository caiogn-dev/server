"""
Management command to validate database integrity and auto-seed if needed.

Usage:
    python manage.py db_healthcheck
    python manage.py db_healthcheck --backup
    python manage.py db_healthcheck --auto-seed
    python manage.py db_healthcheck --backup --auto-seed
"""
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command
from apps.stores.models import Store, StoreDeliveryZone

logger = logging.getLogger(__name__)

REQUIRED_STORES = ['ce-saladas', 'pastita', 'kero-kero']
MIN_PRODUCTS_PER_STORE = 5
MIN_ZONES = 60


class Command(BaseCommand):
    help = 'Validate database integrity and auto-seed if needed.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Create database backup.',
        )
        parser.add_argument(
            '--auto-seed',
            action='store_true',
            help='Auto-seed if stores are missing.',
        )

    def handle(self, *args, **options):
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.WARNING('DATABASE HEALTHCHECK'))
        self.stdout.write('=' * 60 + '\n')

        # Check stores
        self.stdout.write('🔍 Verificando lojas...')
        missing_stores = []
        store_status = {}

        for slug in REQUIRED_STORES:
            try:
                store = Store.objects.get(slug=slug)
                products = store.products.filter(status='active').count()
                zones = StoreDeliveryZone.objects.filter(store=store).count()
                store_status[slug] = {
                    'exists': True,
                    'products': products,
                    'zones': zones,
                }
                status = '✅' if products >= MIN_PRODUCTS_PER_STORE else '⚠️'
                self.stdout.write(
                    f'  {status} {store.name}: {products} produtos, {zones} zonas'
                )
            except Store.DoesNotExist:
                missing_stores.append(slug)
                store_status[slug] = {'exists': False, 'products': 0, 'zones': 0}
                self.stdout.write(f'  ❌ {slug}: LOJA NÃO EXISTE')

        # Global check
        total_stores = Store.objects.count()
        total_zones = StoreDeliveryZone.objects.count()
        self.stdout.write(f'\n📊 Total: {total_stores} lojas, {total_zones} zonas\n')

        # Auto-seed if needed
        if missing_stores and options['auto_seed']:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Lojas faltando: {", ".join(missing_stores)}')
            )
            self.stdout.write('🔄 Executando seed automático...\n')
            try:
                call_command('populate_ce_saladas_menu', '--force')
                call_command('populate_pastita_menu', '--force')
                call_command('populate_kero_kero_menu', '--force')
                call_command('populate_delivery_zones')
                self.stdout.write(
                    self.style.SUCCESS('\n✅ Seed automático completado!')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'\n❌ Erro ao executar seed: {str(e)}')
                )
                raise

        # Backup if requested
        if options['backup']:
            self.stdout.write('\n💾 Criando backup...')
            try:
                backup_script = Path(settings.BASE_DIR) / 'scripts' / 'backup_database.sh'
                if backup_script.exists():
                    result = subprocess.run(
                        ['bash', str(backup_script)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        self.stdout.write(self.style.SUCCESS('✅ Backup criado'))
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Erro no backup: {result.stderr}')
                        )
                else:
                    self.stdout.write(self.style.WARNING('⚠️  Script de backup não encontrado'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Erro ao fazer backup: {str(e)}'))

        # Final status
        self.stdout.write('\n' + '=' * 60)
        if missing_stores:
            self.stdout.write(
                self.style.WARNING('⚠️  AVISO: Lojas faltando (crie com populate_*_menu)')
            )
            self.stdout.write(f'   Faltando: {", ".join(missing_stores)}')
            self.stdout.write('   Execute: python manage.py populate_ce_saladas_menu --force')
        else:
            self.stdout.write(self.style.SUCCESS('✅ HEALTHCHECK OK'))
        self.stdout.write('=' * 60 + '\n')
