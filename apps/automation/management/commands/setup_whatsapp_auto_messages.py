"""
Management command to ensure WhatsApp auto messages exist for companies.
Usage: python manage.py setup_whatsapp_auto_messages [--company-id=<uuid> | --account-id=<uuid> | --all] [--force]
"""
from django.core.management.base import BaseCommand
from apps.automation.models import CompanyProfile
from apps.automation.services import AutomationService


class Command(BaseCommand):
    help = 'Ensure WhatsApp auto messages are created for company profiles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=str,
            help='CompanyProfile UUID to target (defaults to --all).'
        )
        parser.add_argument(
            '--account-id',
            type=str,
            help='WhatsAppAccount UUID to target (falls back to CompanyProfile).'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Populate auto messages for every active company profile.'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recreate auto messages even if they already exist.'
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        account_id = options.get('account_id')
        force = options.get('force')
        apply_all = options.get('all')

        service = AutomationService()
        targets = []

        if company_id:
            try:
                profile = CompanyProfile.objects.get(id=company_id, is_active=True)
                targets = [profile]
            except CompanyProfile.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'CompanyProfile {company_id} not found.'))
                return
        elif account_id:
            try:
                profile = CompanyProfile.objects.get(account_id=account_id, is_active=True)
                targets = [profile]
            except CompanyProfile.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'CompanyProfile for account {account_id} not found.'))
                return
        elif apply_all:
            targets = list(CompanyProfile.objects.filter(is_active=True).select_related('account'))
        else:
            self.stderr.write(self.style.ERROR('Provide --company-id, --account-id or --all.'))
            return

        created_total = 0
        replaced_total = 0

        for profile in targets:
            result = service.ensure_auto_messages(profile, force=force)
            created_total += result.get('created', 0)
            replaced_total += result.get('replaced', 0)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{profile.company_name} ({profile.account.phone_number}): "
                    f"created={result.get('created', 0)} replaced={result.get('replaced', 0)}"
                )
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Total profiles processed: {len(targets)} | created: {created_total} | replaced: {replaced_total}'
        ))
