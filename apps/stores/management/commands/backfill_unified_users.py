"""
Backfill: cria/linka UnifiedUser para StoreCustomers órfãos (unified_user=None).

Clientes cadastrados no "Novo Pedido" antes do fix de sync ficaram sem UnifiedUser
e não apareciam na busca CRM. Este comando os torna pesquisáveis. Idempotente.

Uso: python manage.py backfill_unified_users [--dry-run]
"""
from django.core.management.base import BaseCommand
from apps.stores.models import StoreCustomer
from apps.users.models import UnifiedUser


class Command(BaseCommand):
    help = "Cria/linka UnifiedUser para StoreCustomers sem unified_user."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        qs = (StoreCustomer.objects
              .filter(unified_user__isnull=True)
              .exclude(phone='')
              .exclude(phone__isnull=True)
              .select_related('user', 'store'))
        linked = created = skipped = 0
        for c in qs:
            name = ''
            if c.user:
                name = (c.user.get_full_name() or c.user.first_name or '').strip()
            name = name or 'Cliente'
            email = ''
            if c.user and c.user.email and not c.user.email.endswith('.invalid'):
                email = c.user.email
            try:
                if dry:
                    self.stdout.write(f'[dry] {c.store.slug} {name} {c.phone}')
                    linked += 1
                    continue
                u, was_created = UnifiedUser.resolve(
                    phone=c.phone, email=email, name=name, django_user=c.user,
                )
                c.unified_user = u
                c.save(update_fields=['unified_user'])
                linked += 1
                created += int(was_created)
            except ValueError:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(
            f'backfill: linked={linked} created={created} skipped={skipped} dry={dry}'
        ))
