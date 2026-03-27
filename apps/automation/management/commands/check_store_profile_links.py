"""
Management command: check_store_profile_links

Validates and optionally repairs Store ↔ CompanyProfile relationships.
Identifies orphaned profiles, broken links, and duplicate mappings.

Usage:
    python manage.py check_store_profile_links            # dry-run report
    python manage.py check_store_profile_links --fix      # repair broken links
    python manage.py check_store_profile_links --verbose  # detailed output
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Validate and repair Store ↔ CompanyProfile relationships'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to repair broken links (default: dry-run only)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print details for every profile checked',
        )

    def handle(self, *args, **options):
        from apps.automation.models import CompanyProfile
        from apps.stores.models import Store
        from apps.whatsapp.models import WhatsAppAccount

        do_fix = options['fix']
        verbose = options['verbose']

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Store ↔ CompanyProfile Health Check ===\n'))

        profiles = CompanyProfile.objects.select_related('store', 'account').all()
        total = profiles.count()

        ok = 0
        no_store = []
        no_account = []
        store_mismatch = []
        duplicates = {}

        for profile in profiles:
            store = profile.store
            account = profile.account

            if not store and not account:
                # Violates DB constraint — shouldn't happen
                no_store.append(profile)
                continue

            if verbose:
                self.stdout.write(
                    f'  Profile {profile.id} | store={store.slug if store else "-"} '
                    f'| account={account.name if account else "-"}'
                )

            # Check for store with no link
            if store and not account:
                # Try to find an account via store's whatsapp_account
                wa = getattr(store, 'whatsapp_account', None)
                if wa and not hasattr(wa, 'company_profile'):
                    no_account.append((profile, wa))

            # Check duplicate store → profile mappings
            if store:
                key = str(store.id)
                if key not in duplicates:
                    duplicates[key] = []
                duplicates[key].append(profile)

            ok += 1

        # Report duplicates
        duplicate_stores = {k: v for k, v in duplicates.items() if len(v) > 1}

        self.stdout.write(f'Total profiles checked : {total}')
        self.stdout.write(f'OK                     : {ok}')
        self.stdout.write(f'No store or account    : {len(no_store)}')
        self.stdout.write(f'Missing account link   : {len(no_account)}')
        self.stdout.write(f'Stores with duplicates : {len(duplicate_stores)}')

        # Report stores with no CompanyProfile
        stores_without_profile = Store.objects.filter(
            is_active=True
        ).exclude(
            id__in=CompanyProfile.objects.exclude(store=None).values_list('store_id', flat=True)
        )
        self.stdout.write(f'Stores without profile : {stores_without_profile.count()}')

        # Details
        if no_store:
            self.stdout.write(self.style.ERROR('\nProfiles with no store AND no account (data integrity issue):'))
            for p in no_store:
                self.stdout.write(f'  - Profile {p.id} (created {p.created_at})')

        if duplicate_stores:
            self.stdout.write(self.style.WARNING('\nStores with multiple CompanyProfiles (should be 1:1):'))
            for store_id, profs in duplicate_stores.items():
                store = profs[0].store
                self.stdout.write(f'  Store "{store.slug}" ({store_id}): {len(profs)} profiles')
                for p in profs:
                    self.stdout.write(f'    - Profile {p.id}')

        if stores_without_profile.exists():
            self.stdout.write(self.style.WARNING('\nActive stores with no CompanyProfile:'))
            for s in stores_without_profile[:20]:
                self.stdout.write(f'  - {s.slug} ({s.id})')

        # Fix mode
        if do_fix:
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- Applying fixes ---'))
            fixed = 0

            with transaction.atomic():
                # Create missing CompanyProfiles for active stores
                for store in stores_without_profile:
                    wa = getattr(store, 'whatsapp_account', None)
                    profile, created = CompanyProfile.objects.get_or_create(
                        store=store,
                        defaults={
                            'account': wa,
                        }
                    )
                    if created:
                        self.stdout.write(
                            self.style.SUCCESS(f'  Created CompanyProfile for store "{store.slug}"')
                        )
                        fixed += 1

                # Repair account links for profiles that have store but no account
                for profile, wa in no_account:
                    profile.account = wa
                    profile.save(update_fields=['account'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Linked account "{wa.name}" to profile {profile.id} (store: {profile.store.slug})'
                        )
                    )
                    fixed += 1

            self.stdout.write(self.style.SUCCESS(f'\n{fixed} fixes applied.'))
        else:
            self.stdout.write(self.style.NOTICE('\nRun with --fix to repair broken links.'))

        self.stdout.write('')
