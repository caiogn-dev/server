"""
Startup helpers that ensure the default WhatsApp account is created and linked to configured stores.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError

from .utils import get_default_whatsapp_account, get_default_whatsapp_account_data

logger = logging.getLogger(__name__)


def ensure_default_whatsapp_account(sender, **kwargs):
    """
    Create the default WhatsApp account after migrations and link it to the stores defined in settings.
    """
    if sender.name != 'apps.whatsapp':
        return

    if not getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE', True):
        return

    if not get_default_whatsapp_account_data():
        logger.debug('Default WhatsApp account setup skipped because configuration is incomplete.')
        return

    try:
        with transaction.atomic():
            get_default_whatsapp_account(create_if_missing=True)
    except OperationalError as exc:
        logger.warning('Default WhatsApp account setup delayed because the database is not ready: %s', exc)


def _link_account_to_stores(account):
    slugs = getattr(settings, 'DEFAULT_WHATSAPP_STORE_SLUGS', [])
    if not slugs:
        return

    from apps.stores.models import Store, StoreIntegration

    stores = Store.objects.filter(slug__in=slugs)
    for store in stores:
        _ensure_store_integration(store, account, StoreIntegration)
        _ensure_store_metadata(store, account)


def _ensure_store_integration(store, account, StoreIntegration):
    integration, created = StoreIntegration.objects.get_or_create(
        store=store,
        integration_type=StoreIntegration.IntegrationType.WHATSAPP,
        defaults={
            'name': f'{store.name} WhatsApp',
            'status': StoreIntegration.IntegrationStatus.ACTIVE,
            'external_id': str(account.id),
            'phone_number_id': account.phone_number_id or '',
            'waba_id': account.waba_id or '',
            'settings': {'auto_linked': True},
            'metadata': {'auto_linked': True},
        }
    )

    changed = False
    if integration.external_id != str(account.id):
        integration.external_id = str(account.id)
        changed = True

    if account.phone_number_id and integration.phone_number_id != account.phone_number_id:
        integration.phone_number_id = account.phone_number_id
        changed = True

    if account.waba_id and integration.waba_id != account.waba_id:
        integration.waba_id = account.waba_id
        changed = True

    if integration.status != StoreIntegration.IntegrationStatus.ACTIVE:
        integration.status = StoreIntegration.IntegrationStatus.ACTIVE
        changed = True

    settings_value = integration.settings or {}
    if settings_value.get('auto_linked') is not True:
        settings_value['auto_linked'] = True
        integration.settings = settings_value
        changed = True

    metadata_value = integration.metadata or {}
    if metadata_value.get('auto_linked') is not True:
        metadata_value['auto_linked'] = True
        integration.metadata = metadata_value
        changed = True

    if changed:
        integration.save()


def _ensure_store_metadata(store, account):
    metadata_key = getattr(settings, 'DEFAULT_WHATSAPP_STORE_METADATA_KEY', 'whatsapp_account_id')
    metadata = store.metadata or {}
    desired_value = metadata.get(metadata_key)
    if desired_value != str(account.id):
        metadata[metadata_key] = str(account.id)
        store.metadata = metadata
        store.save(update_fields=['metadata'])


def link_default_whatsapp_account_to_stores(sender, **kwargs):
    """
    After store migrations run, link the configured stores to the default WhatsApp account.
    """
    if sender.name != 'apps.stores':
        return

    slugs = getattr(settings, 'DEFAULT_WHATSAPP_STORE_SLUGS', [])
    if not slugs:
        return

    if not get_default_whatsapp_account_data():
        logger.debug('Skipping store linking because default WhatsApp account configuration is incomplete.')
        return

    allow_creation = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_AUTO_CREATE', False)
    account = get_default_whatsapp_account(create_if_missing=allow_creation)
    if account:
        _link_account_to_stores(account)
