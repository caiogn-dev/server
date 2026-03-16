"""
Management command to fix duplicate CompanyProfile issues.
Usage: python manage.py fix_duplicate_profiles [--store-slug=<slug>] [--all]
"""
from django.core.management.base import BaseCommand
from apps.stores.models import Store
from apps.automation.models import CompanyProfile


class Command(BaseCommand):
    help = 'Fix duplicate CompanyProfile issues and ensure proper WhatsApp account linkage.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store-slug',
            type=str,
            help='Store slug to fix (e.g., ce-saladas)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fix all stores'
        )

    def handle(self, *args, **options):
        store_slug = options.get('store_slug')
        apply_all = options.get('all')

        # Get stores to fix
        if store_slug:
            stores = Store.objects.filter(slug=store_slug)
        elif apply_all:
            stores = Store.objects.filter(is_active=True)
        else:
            self.stderr.write(self.style.ERROR('Provide --store-slug or --all'))
            return

        for store in stores:
            self.stdout.write(f'\nProcessing store: {store.name} ({store.slug})')
            
            # 1. Find all profiles for this store
            profiles = CompanyProfile.objects.filter(store=store)
            self.stdout.write(f'  Found {profiles.count()} profiles for this store')
            
            # 2. Find profiles with the same WhatsApp account
            if store.whatsapp_account_id:
                account_profiles = CompanyProfile.objects.filter(
                    account_id=store.whatsapp_account_id
                )
                self.stdout.write(f'  Found {account_profiles.count()} profiles with WhatsApp account {store.whatsapp_account_id}')
                
                if account_profiles.count() > 1:
                    self.stdout.write(self.style.WARNING(f'  ⚠ Multiple profiles found for same WhatsApp account!'))
                    
                    # Keep the first one, remove account from others
                    primary_profile = account_profiles.first()
                    self.stdout.write(f'  Primary profile: {primary_profile.id}')
                    
                    for profile in account_profiles.exclude(id=primary_profile.id):
                        self.stdout.write(f'  Removing account from duplicate profile: {profile.id}')
                        profile.account_id = None
                        profile.save(update_fields=['account_id', 'updated_at'])
            
            # 3. Ensure the store's profile has the WhatsApp account
            if store.whatsapp_account_id:
                store_profile = profiles.first()
                if store_profile and not store_profile.account_id:
                    # Check if account is free
                    existing = CompanyProfile.objects.filter(
                        account_id=store.whatsapp_account_id
                    ).first()
                    
                    if not existing:
                        store_profile.account_id = store.whatsapp_account_id
                        store_profile.save(update_fields=['account_id', 'updated_at'])
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Linked WhatsApp account to profile'))
                    else:
                        self.stdout.write(f'  Account already linked to profile {existing.id}')
            
            # 4. Final state
            final_profiles = CompanyProfile.objects.filter(store=store)
            for profile in final_profiles:
                self.stdout.write(f'  Profile {profile.id}: account_id={profile.account_id}')

        self.stdout.write(self.style.SUCCESS('\n✓ Done!'))
