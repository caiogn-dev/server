from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.stores.models import StoreCart


class Command(BaseCommand):
    help = 'Remove carrinhos guest abandonados e carrinhos inativos antigos'

    def add_arguments(self, parser):
        parser.add_argument('--guest-days', type=int, default=30,
                            help='Deletar carrinhos guest mais antigos que N dias (default: 30)')
        parser.add_argument('--auth-days', type=int, default=90,
                            help='Deletar carrinhos autenticados mais antigos que N dias (default: 90)')
        parser.add_argument('--inactive-days', type=int, default=7,
                            help='Deletar carrinhos is_active=False mais antigos que N dias (default: 7)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Apenas conta, não deleta')

    def handle(self, *args, **options):
        now = timezone.now()
        guest_cutoff = now - timedelta(days=options['guest_days'])
        auth_cutoff = now - timedelta(days=options['auth_days'])
        inactive_cutoff = now - timedelta(days=options['inactive_days'])

        guest_qs = StoreCart.objects.filter(
            user__isnull=True,
            is_active=True,
            updated_at__lt=guest_cutoff,
        )
        auth_qs = StoreCart.objects.filter(
            user__isnull=False,
            is_active=True,
            updated_at__lt=auth_cutoff,
        )
        inactive_qs = StoreCart.objects.filter(
            is_active=False,
            updated_at__lt=inactive_cutoff,
        )

        self.stdout.write(f'Carrinhos guest >{options["guest_days"]}d: {guest_qs.count()}')
        self.stdout.write(f'Carrinhos auth >{options["auth_days"]}d: {auth_qs.count()}')
        self.stdout.write(f'Carrinhos inativos >{options["inactive_days"]}d: {inactive_qs.count()}')
        total = guest_qs.count() + auth_qs.count() + inactive_qs.count()
        self.stdout.write(f'Total elegível: {total}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN — nada deletado'))
            return

        deleted_guest, _ = guest_qs.delete()
        deleted_auth, _ = auth_qs.delete()
        deleted_inactive, _ = inactive_qs.delete()
        total_deleted = deleted_guest + deleted_auth + deleted_inactive

        self.stdout.write(self.style.SUCCESS(f'Deletados: {total_deleted} carrinhos'))
