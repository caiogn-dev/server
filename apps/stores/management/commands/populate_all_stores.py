"""
Master command to populate all 3 stores (Cê Saladas, Pastita, Kero Kero).

Usage:
    python manage.py populate_all_stores --all              # Populate all 3 stores
    python manage.py populate_all_stores --store=ce-saladas # Populate only Cê Saladas
    python manage.py populate_all_stores --store=pastita --store=kero-kero
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from io import StringIO

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Master command to populate all 3 stores with data'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Populate all 3 stores (default)')
        parser.add_argument('--store', action='append', dest='stores', help='Populate specific store (ce-saladas, pastita, kero-kero). Can be specified multiple times.')
        parser.add_argument('--force', action='store_true', help='Force overwrite of existing data')

    def handle(self, *args, **options):
        stores_to_populate = []
        force = options.get('force', False)

        if options.get('all'):
            stores_to_populate = ['ce-saladas', 'pastita', 'kero-kero']
        elif options.get('stores'):
            stores_to_populate = options['stores']
        else:
            stores_to_populate = ['ce-saladas', 'pastita', 'kero-kero']

        valid_stores = {'ce-saladas', 'pastita', 'kero-kero'}
        for store in stores_to_populate:
            if store not in valid_stores:
                raise CommandError(f"Unknown store: {store}. Valid: {valid_stores}")

        store_commands = {
            'ce-saladas': 'populate_ce_saladas_menu',
            'pastita': 'populate_pastita_menu',
            'kero-kero': 'populate_kero_kero_menu',
        }

        self.stdout.write(self.style.HTTP_SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.HTTP_SUCCESS('🚀 INICIANDO POPULAÇÃO DAS 3 LOJAS'))
        self.stdout.write(self.style.HTTP_SUCCESS('='*70 + '\n'))

        results = {}
        for store_slug in stores_to_populate:
            command_name = store_commands[store_slug]

            self.stdout.write(f'\n📦 Populando: {store_slug.upper()}')
            self.stdout.write('-' * 70)

            try:
                out = StringIO()
                call_command(command_name, '--force' if force else '', stdout=out, stderr=out)
                self.stdout.write(out.getvalue())
                results[store_slug] = 'SUCCESS'
            except Exception as e:
                logger.exception(f"Erro ao popular {store_slug}")
                self.stdout.write(self.style.ERROR(f'❌ ERRO: {e}'))
                results[store_slug] = f'FAILED: {e}'

        self.stdout.write(self.style.HTTP_SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.HTTP_SUCCESS('📊 RESUMO DA EXECUÇÃO'))
        self.stdout.write(self.style.HTTP_SUCCESS('='*70 + '\n'))

        for store_slug, status in results.items():
            if status == 'SUCCESS':
                self.stdout.write(self.style.SUCCESS(f'✅ {store_slug}: {status}'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ {store_slug}: {status}'))

        self.stdout.write('\n')
