"""
Management command to migrate CompanyProfile data to new unified architecture.

This command:
1. Links CompanyProfile to Store via the new store FK
2. Links Store to WhatsAppAccount via the new whatsapp_account FK
3. Validates data consistency

Usage:
    python manage.py migrate_company_profiles [--dry-run]
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.stores.models import Store
from apps.automation.models import CompanyProfile
from apps.whatsapp.models import WhatsAppAccount

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate CompanyProfile data to unified Store architecture'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if data inconsistencies are found',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.NOTICE('=' * 60))
        self.stdout.write(self.style.NOTICE('CompanyProfile Migration Tool'))
        self.stdout.write(self.style.NOTICE('=' * 60))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Statistics
        stats = {
            'profiles_total': 0,
            'profiles_linked': 0,
            'profiles_skipped': 0,
            'stores_linked': 0,
            'inconsistencies': 0,
        }
        
        # Step 1: Link CompanyProfile to Store
        self.stdout.write('\nStep 1: Linking CompanyProfile to Store...')
        
        profiles = CompanyProfile.objects.filter(store__isnull=True)
        stats['profiles_total'] = profiles.count()
        
        for profile in profiles:
            try:
                with transaction.atomic():
                    store = self._find_store_for_profile(profile)
                    
                    if store:
                        if not dry_run:
                            profile.store = store
                            profile.save(update_fields=['store'])
                        stats['profiles_linked'] += 1
                        self.stdout.write(f'  Linked: {profile} → {store.name}')
                    else:
                        stats['profiles_skipped'] += 1
                        self.stdout.write(
                            self.style.WARNING(f'  Skipped: {profile} (no matching store found)')
                        )
                        
            except Exception as e:
                stats['inconsistencies'] += 1
                self.stdout.write(self.style.ERROR(f'  Error: {profile} - {e}'))
                if not force:
                    raise
        
        # Step 2: Link Store to WhatsAppAccount
        self.stdout.write('\nStep 2: Linking Store to WhatsAppAccount...')
        
        stores = Store.objects.filter(whatsapp_account__isnull=True)
        
        for store in stores:
            try:
                with transaction.atomic():
                    account = self._find_account_for_store(store)
                    
                    if account:
                        if not dry_run:
                            store.whatsapp_account = account
                            store.save(update_fields=['whatsapp_account'])
                        stats['stores_linked'] += 1
                        self.stdout.write(f'  Linked: {store.name} → {account.phone_number}')
                        
            except Exception as e:
                stats['inconsistencies'] += 1
                self.stdout.write(self.style.ERROR(f'  Error: {store.name} - {e}'))
                if not force:
                    raise
        
        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.NOTICE('Migration Summary'))
        self.stdout.write('=' * 60)
        self.stdout.write(f"Total profiles processed: {stats['profiles_total']}")
        self.stdout.write(f"Profiles linked to store: {stats['profiles_linked']}")
        self.stdout.write(f"Profiles skipped: {stats['profiles_skipped']}")
        self.stdout.write(f"Stores linked to WhatsApp: {stats['stores_linked']}")
        
        if stats['inconsistencies'] > 0:
            self.stdout.write(
                self.style.WARNING(f"Inconsistencies found: {stats['inconsistencies']}")
            )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY RUN. No changes were made.'))
            self.stdout.write('Run without --dry-run to apply changes.')
        else:
            self.stdout.write(self.style.SUCCESS('\nMigration completed successfully!'))
    
    def _find_store_for_profile(self, profile: CompanyProfile) -> Store:
        """Find the Store that should be linked to this CompanyProfile."""
        # Strategy 1: Match by WhatsApp account
        if profile.account_id:
            # Try to find store that has this account in integrations
            from apps.stores.models import StoreIntegration
            integration = StoreIntegration.objects.filter(
                integration_type=StoreIntegration.IntegrationType.WHATSAPP,
                external_id=str(profile.account_id)
            ).first()
            
            if integration:
                return integration.store
        
        # Strategy 2: Match by name similarity
        if profile._company_name:
            store = Store.objects.filter(
                name__iexact=profile._company_name,
                is_active=True
            ).first()
            
            if store:
                return store
        
        # Strategy 3: Match by phone number
        if profile.account_id:
            account = WhatsAppAccount.objects.filter(id=profile.account_id).first()
            if account:
                store = Store.objects.filter(
                    whatsapp_number=account.phone_number,
                    is_active=True
                ).first()
                
                if store:
                    return store
        
        return None
    
    def _find_account_for_store(self, store: Store) -> WhatsAppAccount:
        """Find the WhatsAppAccount that should be linked to this Store."""
        # Strategy 1: Check if store has automation_profile
        if hasattr(store, 'automation_profile'):
            profile = store.automation_profile
            if profile and profile.account_id:
                return profile.account
        
        # Strategy 2: Check integrations
        from apps.stores.models import StoreIntegration
        integration = StoreIntegration.objects.filter(
            store=store,
            integration_type=StoreIntegration.IntegrationType.WHATSAPP,
            status=StoreIntegration.IntegrationStatus.ACTIVE
        ).first()
        
        if integration and integration.phone_number_id:
            account = WhatsAppAccount.objects.filter(
                phone_number_id=integration.phone_number_id
            ).first()
            
            if account:
                return account
        
        # Strategy 3: Match by whatsapp_number
        if store.whatsapp_number:
            account = WhatsAppAccount.objects.filter(
                phone_number=store.whatsapp_number
            ).first()
            
            if account:
                return account
        
        return None
