from django.core.management.base import BaseCommand
from apps.stores.models import StoreCustomer, StoreCustomerAddress


class Command(BaseCommand):
    help = 'Migra StoreCustomer.addresses JSON → tabela StoreCustomerAddress'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        customers = StoreCustomer.objects.exclude(addresses=[]).exclude(addresses__isnull=True)
        self.stdout.write(f'Customers com JSON addresses: {customers.count()}')
        migrated = 0
        skipped = 0

        for customer in customers:
            addresses = customer.addresses or []
            if not isinstance(addresses, list):
                skipped += 1
                continue
            for i, addr in enumerate(addresses):
                if not isinstance(addr, dict):
                    skipped += 1
                    continue
                if not addr.get('street') and not addr.get('zip_code'):
                    skipped += 1
                    continue
                is_default = (i == (customer.default_address_index or 0))
                if not options['dry_run']:
                    existing = StoreCustomerAddress.objects.filter(
                        customer=customer,
                        street=addr.get('street', ''),
                        number=addr.get('number', ''),
                    ).first()
                    if not existing:
                        existing = StoreCustomerAddress.objects.create(
                            customer=customer,
                            street=addr.get('street', ''),
                            number=addr.get('number', ''),
                            complement=addr.get('complement', ''),
                            neighborhood=addr.get('neighborhood', ''),
                            city=addr.get('city', ''),
                            state=addr.get('state', ''),
                            zip_code=addr.get('zip_code', ''),
                            reference=addr.get('reference', ''),
                            is_default=is_default,
                        )
                    if is_default:
                        StoreCustomerAddress.objects.filter(
                            customer=customer, is_default=True,
                        ).exclude(pk=existing.pk).update(is_default=False)
                migrated += 1

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if options["dry_run"] else ""}Migrados: {migrated}, Ignorados: {skipped}'
        ))
