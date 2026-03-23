"""
Signals for Automation app.

Handles automatic creation and linking of CompanyProfile with Store and WhatsAppAccount.
"""
import logging
from django.db import connection
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _company_profile_table_ready() -> bool:
    """
    Guard post_save hooks during deploys where code is ahead of the database.

    Store creation must not fail just because the automation schema has not been
    migrated yet.
    """
    try:
        return 'company_profiles' in connection.introspection.table_names()
    except Exception:
        return False


@receiver(post_save, sender='stores.Store')
def create_or_link_company_profile_for_store(sender, instance, created, **kwargs):
    """
    When a Store is created or saved, ensure it has a linked CompanyProfile.
    
    If the store has a whatsapp_account, also link the profile to that account.
    """
    from .models import CompanyProfile

    if not _company_profile_table_ready():
        logger.warning(
            "Skipping CompanyProfile sync for Store %s because table %s is not available yet.",
            instance.pk,
            CompanyProfile._meta.db_table,
        )
        return

    try:
        with transaction.atomic():
            # Check if store already has a profile
            if hasattr(instance, 'automation_profile') and instance.automation_profile:
                profile = instance.automation_profile
                
                # Update profile with store data if needed
                if profile._company_name != instance.name:
                    profile._company_name = instance.name
                    profile._description = instance.description
                    profile.save(update_fields=['_company_name', '_description', 'updated_at'])
                
                # Link to WhatsApp account if store has one
                if instance.whatsapp_account and profile.account != instance.whatsapp_account:
                    profile.account = instance.whatsapp_account
                    profile.save(update_fields=['account', 'updated_at'])
                    logger.info(f"Linked CompanyProfile {profile.id} to WhatsApp account {instance.whatsapp_account.id}")
                
                return

            # Create new profile for store
            profile_data = {
                'store': instance,
                '_company_name': instance.name,
                '_description': instance.description or '',
            }
            
            # If store has WhatsApp account, link it
            if instance.whatsapp_account:
                # Check if the WhatsApp account already has a profile
                if hasattr(instance.whatsapp_account, 'company_profile') and instance.whatsapp_account.company_profile:
                    # Link existing profile to store
                    existing_profile = instance.whatsapp_account.company_profile
                    existing_profile.store = instance
                    existing_profile._company_name = instance.name
                    existing_profile._description = instance.description or ''
                    existing_profile.save(update_fields=['store', '_company_name', '_description', 'updated_at'])
                    logger.info(f"Linked existing CompanyProfile {existing_profile.id} to Store {instance.slug}")
                    return
                else:
                    profile_data['account'] = instance.whatsapp_account
            
            profile = CompanyProfile.objects.create(**profile_data)
            logger.info(f"Created CompanyProfile {profile.id} for Store {instance.slug}")
            
            # Create default auto messages for the new profile
            try:
                from .services import AutomationService
                service = AutomationService()
                result = service.ensure_auto_messages(profile)
                logger.info(f"Created {result.get('created', 0)} default auto messages for Store {instance.slug}")
            except Exception as msg_error:
                logger.error(f"Error creating auto messages for Store {instance.slug}: {msg_error}")
        
    except Exception as e:
        logger.error(f"Error creating/linking CompanyProfile for Store {instance.id}: {e}", exc_info=True)


@receiver(post_save, sender='whatsapp.WhatsAppAccount')
def create_or_link_company_profile_for_account(sender, instance, created, **kwargs):
    """
    When a WhatsAppAccount is created, ensure it has a linked CompanyProfile.
    
    If the account is linked to a Store (via stores relationship), use that store's data.
    """
    from .models import CompanyProfile

    if not _company_profile_table_ready():
        logger.warning(
            "Skipping CompanyProfile sync for WhatsAppAccount %s because table %s is not available yet.",
            instance.pk,
            CompanyProfile._meta.db_table,
        )
        return

    try:
        with transaction.atomic():
            # Check if account already has a profile
            if hasattr(instance, 'company_profile') and instance.company_profile:
                return

            # Check if there's a store linked to this account
            store = None
            if hasattr(instance, 'stores') and instance.stores.exists():
                store = instance.stores.first()
            
            if store:
                # If store has a profile, link it to this account
                if hasattr(store, 'automation_profile') and store.automation_profile:
                    profile = store.automation_profile
                    profile.account = instance
                    profile.save(update_fields=['account', 'updated_at'])
                    logger.info(f"Linked CompanyProfile to WhatsApp account {instance.id} from Store {store.slug}")
                    return
            
            # Create new profile for account
            profile_data = {
                'account': instance,
                '_company_name': instance.name,
            }
            
            if store:
                profile_data['store'] = store
                profile_data['_company_name'] = store.name
                profile_data['_description'] = store.description or ''
            
            profile = CompanyProfile.objects.create(**profile_data)
            logger.info(f"Created CompanyProfile {profile.id} for WhatsApp account {instance.id}")
        
    except Exception as e:
        logger.error(f"Error creating/linking CompanyProfile for WhatsApp account {instance.id}: {e}", exc_info=True)


@receiver(post_save, sender='stores.Store')
def sync_store_whatsapp_account(sender, instance, **kwargs):
    """
    When a Store is saved with a whatsapp_account, ensure bidirectional consistency.
    """
    if instance.whatsapp_account:
        # Update the whatsapp account's stores relationship if needed
        try:
            # This triggers the signal above if the account is new
            pass
        except Exception as e:
            logger.warning(f"Error syncing Store-WhatsApp relationship: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# CompanyProfile → sync AI settings to WhatsApp account
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='automation.CompanyProfile')
def sync_company_profile_ai_to_account(sender, instance, **kwargs):
    """
    Quando CompanyProfile é salvo (inclusive via Django Admin), propaga
    as configurações de IA (default_agent, auto_response_enabled) para a
    conta WhatsApp vinculada.

    Isso garante que WhatsAppAccount.default_agent e auto_response_enabled
    fiquem sempre sincronizados, independente de como o perfil foi editado.
    """
    try:
        instance.sync_ai_settings_to_account(save=True)
    except Exception as exc:
        logger.warning(
            'sync_company_profile_ai_to_account: failed for profile %s — %s',
            instance.pk, exc,
        )


# ──────────────────────────────────────────────────────────────────────────────
# StoreOrder → WhatsApp notifications
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='stores.StoreOrder')
def trigger_order_status_notification(sender, instance, created, update_fields, **kwargs):
    """
    Fire a WhatsApp notification whenever an order is created or its status changes.

    Triggers:
    - On creation         → notify_order_status_change('received')
    - On status update    → notify_order_status_change(<new_status>)
    - On 'delivered'      → schedule_feedback_request (30 min later)

    The notification tasks are safe to call even when no AutoMessage template
    exists for a given event_type — they log a debug message and exit silently.
    """
    from django.db import transaction

    # Avoid circular imports: import tasks lazily
    def _dispatch_status(status):
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        notify_order_status_change.delay(str(instance.id), status)

    def _dispatch_feedback():
        from apps.whatsapp.tasks.automation_tasks import schedule_feedback_request
        schedule_feedback_request.delay(str(instance.id))

    try:
        if created:
            transaction.on_commit(lambda: _dispatch_status('received'))
            return

        # Only trigger when 'status' was part of the save
        if update_fields is not None and 'status' not in update_fields:
            return

        transaction.on_commit(lambda: _dispatch_status(instance.status))

        if instance.status == 'delivered':
            transaction.on_commit(_dispatch_feedback)

    except Exception as e:
        logger.warning(f"Error dispatching order notification for order {instance.pk}: {e}")
