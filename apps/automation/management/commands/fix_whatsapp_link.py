"""
Management command to fix WhatsApp account linkage for stores.
Usage: python manage.py fix_whatsapp_link [--store-slug=<slug>] [--all]
"""
from django.core.management.base import BaseCommand
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount
from apps.automation.models import CompanyProfile


class Command(BaseCommand):
    help = 'Fix WhatsApp account linkage for stores and create CompanyProfile if needed.'

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
        parser.add_argument(
            '--whatsapp-account-id',
            type=str,
            help='WhatsApp Account ID to link (if not provided, uses first available)'
        )

    def handle(self, *args, **options):
        store_slug = options.get('store_slug')
        apply_all = options.get('all')
        whatsapp_account_id = options.get('whatsapp_account_id')

        # Get WhatsApp account
        wa_account = None
        if whatsapp_account_id:
            try:
                wa_account = WhatsAppAccount.objects.get(id=whatsapp_account_id)
            except WhatsAppAccount.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'WhatsApp account {whatsapp_account_id} not found.'))
                return
        else:
            wa_account = WhatsAppAccount.objects.filter(is_active=True).first()
            if not wa_account:
                self.stderr.write(self.style.ERROR('No active WhatsApp account found.'))
                return
        
        self.stdout.write(f'Using WhatsApp account: {wa_account.id} ({wa_account.phone_number})')

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
            
            # 1. Link WhatsApp account to store
            if store.whatsapp_account_id != wa_account.id:
                store.whatsapp_account = wa_account
                store.save(update_fields=['whatsapp_account', 'updated_at'])
                self.stdout.write(self.style.SUCCESS(f'  ✓ Linked WhatsApp account to store'))
            else:
                self.stdout.write(f'  - WhatsApp account already linked')
            
            # 2. Get or create CompanyProfile
            profile = None
            if hasattr(store, 'automation_profile') and store.automation_profile:
                profile = store.automation_profile
                self.stdout.write(f'  - Found existing CompanyProfile: {profile.id}')
            else:
                profile = CompanyProfile.objects.filter(store=store).first()
                if profile:
                    self.stdout.write(f'  - Found CompanyProfile via query: {profile.id}')
            
            if not profile:
                profile = CompanyProfile.objects.create(
                    store=store,
                    account=wa_account,
                    _company_name=store.name,
                )
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created CompanyProfile: {profile.id}'))
            
            # 3. Link WhatsApp account to profile
            if profile.account_id != wa_account.id:
                profile.account = wa_account
                profile.save(update_fields=['account', 'updated_at'])
                self.stdout.write(self.style.SUCCESS(f'  ✓ Linked WhatsApp account to profile'))
            
            # 4. Create default auto messages
            from apps.automation.services import AutomationService
            service = AutomationService()
            result = service.ensure_auto_messages(profile)
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Auto messages: created={result.get("created", 0)}, existing={result.get("replaced", 0)}'
            ))
            
            # 5. Verify
            self.stdout.write(f'\n  Final state:')
            self.stdout.write(f'    Store.whatsapp_account_id: {store.whatsapp_account_id}')
            self.stdout.write(f'    Profile.account_id: {profile.account_id}')
            self.stdout.write(f'    Profile.order_status_notification_enabled: {profile.order_status_notification_enabled}')
            
            auto_messages_count = profile.auto_messages.filter(is_active=True).count()
            self.stdout.write(f'    Active auto messages: {auto_messages_count}')

        self.stdout.write(self.style.SUCCESS('\n✓ Done!'))
