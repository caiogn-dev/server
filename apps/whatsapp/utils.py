"""
Utility helpers for default WhatsApp account management.
"""
from typing import Dict, Optional
import logging
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model

from .models import WhatsAppAccount
from .repositories import WhatsAppAccountRepository

logger = logging.getLogger(__name__)


def get_default_whatsapp_account_data() -> Optional[Dict[str, str]]:
    """
    Return sanitized configuration for the default WhatsApp account.
    """
    account_id = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_ID', '').strip()
    phone_number = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER', '').strip()
    display_number = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_DISPLAY_NUMBER', '').strip()
    phone_number_id = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_PHONE_NUMBER_ID', '').strip()
    waba_id = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_WABA_ID', '').strip()
    access_token = getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_ACCESS_TOKEN', '').strip()

    has_lookup_data = bool(account_id or phone_number_id or waba_id or phone_number)
    has_creation_data = bool(phone_number and access_token)

    if not has_lookup_data and not has_creation_data:
        logger.debug(
            'Default WhatsApp account configuration is missing (provide account ID or phone number + token).'
        )
        return None

    return {
        'account_id': account_id,
        'name': getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_NAME', 'WhatsApp Business Account'),
        'phone_number': phone_number,
        'display_phone_number': display_number or phone_number,
        'phone_number_id': phone_number_id,
        'waba_id': waba_id,
        'access_token': access_token,
        'owner_email': getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_OWNER_EMAIL', '').strip(),
        'status': getattr(settings, 'DEFAULT_WHATSAPP_ACCOUNT_STATUS', 'active').strip().lower(),
    }


def get_default_whatsapp_account(create_if_missing: bool = False) -> Optional[WhatsAppAccount]:
    """
    Return the default WhatsApp account if configured. If requested, create it.
    """
    data = get_default_whatsapp_account_data()
    if not data:
        return None

    repo = WhatsAppAccountRepository()
    account = None

    account_id = data.get('account_id')
    if account_id:
        try:
            account = repo.get_by_id(UUID(account_id))
        except (ValueError, AttributeError):
            account = None

    if not account and data.get('phone_number_id'):
        account = repo.get_by_phone_number_id(data['phone_number_id'])

    if not account and data.get('phone_number'):
        account = repo.get_by_phone_number(data['phone_number'])

    if account:
        updated = _sync_account(account, data)
        if updated:
            account.save()
        return account

    if create_if_missing and data.get('phone_number') and data.get('access_token'):
        return _create_default_whatsapp_account(data)

    return None


def _create_default_whatsapp_account(data: Dict[str, str]) -> Optional[WhatsAppAccount]:
    if not data.get('access_token'):
        logger.warning('Default WhatsApp account creation skipped because access token is missing.')
        return None
    if not data.get('phone_number'):
        logger.warning('Default WhatsApp account creation skipped because phone number is missing.')
        return None

    status = _resolve_account_status(data.get('status'))
    owner = _get_account_owner(data.get('owner_email'))

    account = WhatsAppAccount(
        name=data.get('name') or 'WhatsApp Business Account',
        phone_number=data['phone_number'],
        display_phone_number=data.get('display_phone_number') or data['phone_number'],
        phone_number_id=data.get('phone_number_id') or '',
        waba_id=data.get('waba_id') or '',
        status=status,
        webhook_verify_token=settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
        owner=owner,
    )
    account.is_active = True
    account.access_token = data['access_token']
    account.metadata = {**(account.metadata or {}), 'auto_created': True}
    account.save()
    logger.info('Created default WhatsApp account %s', account.id)
    return account


def _sync_account(account: WhatsAppAccount, data: Dict[str, str]) -> bool:
    updated = False

    if data.get('phone_number') and account.phone_number != data['phone_number']:
        account.phone_number = data['phone_number']
        updated = True

    display_number = data.get('display_phone_number')
    if display_number and account.display_phone_number != display_number:
        account.display_phone_number = display_number
        updated = True

    phone_number_id = data.get('phone_number_id')
    if phone_number_id and account.phone_number_id != phone_number_id:
        account.phone_number_id = phone_number_id
        updated = True

    waba_id = data.get('waba_id')
    if waba_id and account.waba_id != waba_id:
        account.waba_id = waba_id
        updated = True

    desired_status = _resolve_account_status(data.get('status'))
    if desired_status and account.status != desired_status:
        account.status = desired_status
        updated = True

    if account.metadata is None:
        account.metadata = {}
    if account.metadata.get('auto_created') is not True:
        account.metadata['auto_created'] = True
        updated = True

    owner = _get_account_owner(data.get('owner_email'))
    if owner and account.owner != owner:
        account.owner = owner
        updated = True

    if data.get('access_token'):
        account.access_token = data['access_token']
        updated = True

    if updated:
        account.is_active = True

    return updated


def _resolve_account_status(status_value: Optional[str]) -> str:
    if not status_value:
        return WhatsAppAccount.AccountStatus.ACTIVE
    normalized = status_value.strip().lower()
    for choice in WhatsAppAccount.AccountStatus.values:
        if normalized == choice:
            return choice
    return WhatsAppAccount.AccountStatus.ACTIVE


def _get_account_owner(owner_email: Optional[str]):
    if not owner_email:
        return None
    User = get_user_model()
    return User.objects.filter(email__iexact=owner_email).first()
