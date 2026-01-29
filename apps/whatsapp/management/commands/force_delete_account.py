"""
Management command to force delete a WhatsApp account and all related data.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from apps.whatsapp.models import WhatsAppAccount


class Command(BaseCommand):
    help = 'Force delete a WhatsApp account and all related data'

    def add_arguments(self, parser):
        parser.add_argument('account_id', type=str, help='UUID of the account to delete')
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )

    def handle(self, *args, **options):
        account_id = options['account_id']
        
        try:
            account = WhatsAppAccount.objects.get(id=account_id)
        except WhatsAppAccount.DoesNotExist:
            # Try by name
            accounts = WhatsAppAccount.objects.filter(name__icontains=account_id)
            if accounts.count() == 0:
                raise CommandError(f'Account not found: {account_id}')
            elif accounts.count() > 1:
                self.stdout.write(self.style.WARNING('Multiple accounts found:'))
                for acc in accounts:
                    self.stdout.write(f'  - {acc.id}: {acc.name} ({acc.phone_number})')
                raise CommandError('Please specify the exact UUID')
            account = accounts.first()
        
        self.stdout.write(f'\nAccount found:')
        self.stdout.write(f'  ID: {account.id}')
        self.stdout.write(f'  Name: {account.name}')
        self.stdout.write(f'  Phone: {account.phone_number}')
        self.stdout.write(f'  Status: {account.status}')
        
        # Count related objects
        counts = {
            'messages': account.messages.count(),
            'webhook_events': account.webhook_events.count(),
            'templates': account.templates.count(),
        }
        
        # Try to count other related objects
        try:
            from apps.conversations.models import Conversation
            counts['conversations'] = Conversation.objects.filter(account=account).count()
        except:
            counts['conversations'] = '?'
            
        try:
            from apps.campaigns.models import Campaign, ContactList
            from apps.automation.models import ScheduledMessage
            counts['campaigns'] = Campaign.objects.filter(account=account).count()
            counts['scheduled_messages'] = ScheduledMessage.objects.filter(account=account).count()
            counts['contact_lists'] = ContactList.objects.filter(account=account).count()
        except:
            counts['campaigns'] = '?'
            
        try:
            from apps.automation.models import CompanyProfile
            counts['company_profiles'] = CompanyProfile.objects.filter(account=account).count()
        except:
            counts['company_profiles'] = '?'

        try:
            from apps.stores.models import StoreIntegration, StoreOrder
            store_ids = StoreIntegration.objects.filter(
                integration_type=StoreIntegration.IntegrationType.WHATSAPP
            ).filter(
                Q(phone_number_id=account.phone_number_id) |
                Q(waba_id=account.waba_id)
            ).values_list('store_id', flat=True)
            store_ids = list(store_ids)
            counts['store_integrations'] = len(store_ids)
            counts['store_orders'] = StoreOrder.objects.filter(store_id__in=store_ids).count()
        except:
            counts['store_integrations'] = '?'
            counts['store_orders'] = '?'
        
        self.stdout.write(f'\nRelated objects to be deleted:')
        for key, value in counts.items():
            self.stdout.write(f'  - {key}: {value}')
        
        if not options['confirm']:
            confirm = input('\nAre you sure you want to delete this account? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
        
        self.stdout.write('\nDeleting...')
        
        deleted_counts = {}
        
        try:
            with transaction.atomic():
                # Delete messages
                deleted_counts['messages'] = account.messages.count()
                account.messages.all().delete()
                self.stdout.write(f'  ✓ Deleted {deleted_counts["messages"]} messages')
                
                # Delete webhook events
                deleted_counts['webhook_events'] = account.webhook_events.count()
                account.webhook_events.all().delete()
                self.stdout.write(f'  ✓ Deleted {deleted_counts["webhook_events"]} webhook events')
                
                # Delete templates
                deleted_counts['templates'] = account.templates.count()
                account.templates.all().delete()
                self.stdout.write(f'  ✓ Deleted {deleted_counts["templates"]} templates')
                
                # Delete conversations
                try:
                    from apps.conversations.models import Conversation
                    conversations = Conversation.objects.filter(account=account)
                    deleted_counts['conversations'] = conversations.count()
                    conversations.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["conversations"]} conversations')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete conversations: {e}'))
                
                # Delete campaigns and related
                try:
                    from apps.campaigns.models import Campaign, ContactList
                    from apps.automation.models import ScheduledMessage
                    campaigns = Campaign.objects.filter(account=account)
                    for campaign in campaigns:
                        campaign.recipients.all().delete()
                    deleted_counts['campaigns'] = campaigns.count()
                    campaigns.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["campaigns"]} campaigns')
                    
                    scheduled = ScheduledMessage.objects.filter(account=account)
                    deleted_counts['scheduled_messages'] = scheduled.count()
                    scheduled.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["scheduled_messages"]} scheduled messages')
                    
                    contact_lists = ContactList.objects.filter(account=account)
                    deleted_counts['contact_lists'] = contact_lists.count()
                    contact_lists.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["contact_lists"]} contact lists')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete campaigns: {e}'))
                
                # Delete automation sessions
                try:
                    from apps.automation.models import CustomerSession
                    sessions = CustomerSession.objects.filter(company__account=account)
                    deleted_counts['automation_sessions'] = sessions.count()
                    sessions.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["automation_sessions"]} automation sessions')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete automation sessions: {e}'))
                
                # Delete company profiles
                try:
                    from apps.automation.models import CompanyProfile
                    profiles = CompanyProfile.objects.filter(account=account)
                    deleted_counts['company_profiles'] = profiles.count()
                    profiles.delete()
                    self.stdout.write(f'  ??? Deleted {deleted_counts["company_profiles"]} company profiles')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete company profiles: {e}'))
                
                # Delete store integrations and orders linked to this WhatsApp account
                try:
                    from apps.stores.models import StoreIntegration, StoreOrder
                    store_ids = StoreIntegration.objects.filter(
                        integration_type=StoreIntegration.IntegrationType.WHATSAPP
                    ).filter(
                        Q(phone_number_id=account.phone_number_id) |
                        Q(waba_id=account.waba_id)
                    ).values_list('store_id', flat=True)
                    store_ids = list(store_ids)
                    deleted_counts['store_orders'] = StoreOrder.objects.filter(store_id__in=store_ids).count()
                    StoreOrder.objects.filter(store_id__in=store_ids).delete()
                    deleted_counts['store_integrations'] = StoreIntegration.objects.filter(
                        store_id__in=store_ids,
                        integration_type=StoreIntegration.IntegrationType.WHATSAPP
                    ).count()
                    StoreIntegration.objects.filter(
                        store_id__in=store_ids,
                        integration_type=StoreIntegration.IntegrationType.WHATSAPP
                    ).delete()
                    self.stdout.write(
                        f'  ??? Deleted {deleted_counts["store_orders"]} store orders and '
                        f'{deleted_counts["store_integrations"]} store integrations'
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete store integrations/orders: {e}'))

                # Delete langflow integrations
                try:
                    from apps.langflow.models import LangflowIntegration
                    integrations = LangflowIntegration.objects.filter(account=account)
                    deleted_counts['langflow_integrations'] = integrations.count()
                    integrations.delete()
                    self.stdout.write(f'  ✓ Deleted {deleted_counts["langflow_integrations"]} langflow integrations')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ! Could not delete langflow integrations: {e}'))
                
                # Finally delete the account
                account_name = account.name
                account.delete()
                self.stdout.write(f'  ✓ Deleted account')
                
            self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully deleted account "{account_name}"'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Error deleting account: {e}'))
            raise CommandError(str(e))
