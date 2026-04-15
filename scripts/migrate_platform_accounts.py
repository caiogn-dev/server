#!/usr/bin/env python
"""
Migration script to consolidate messaging accounts into unified PlatformAccount model.

This script migrates data from:
- whatsapp.WhatsAppAccount -> messaging.PlatformAccount
- instagram.InstagramAccount -> messaging.PlatformAccount
- messaging.MessengerAccount -> messaging.PlatformAccount
- messaging_v2.PlatformAccount -> messaging.PlatformAccount (if exists)
- stores.StoreIntegration (messaging platforms) -> messaging.PlatformAccount

Run with: python manage.py runscript migrate_platform_accounts
"""

import logging
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def migrate_whatsapp_accounts():
    """Migrate WhatsApp accounts to PlatformAccount."""
    from apps.whatsapp.models import WhatsAppAccount
    from apps.messaging.models import PlatformAccount
    
    logger.info("Starting WhatsApp account migration...")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for wa_account in WhatsAppAccount.objects.all():
        try:
            # Check if already migrated
            existing = PlatformAccount.objects.filter(
                platform=PlatformAccount.PlatformType.WHATSAPP,
                external_id=wa_account.phone_number_id
            ).first()
            
            if existing:
                logger.info(f"Skipping already migrated WhatsApp account: {wa_account.name}")
                skipped += 1
                continue
            
            # Create unified account
            with transaction.atomic():
                platform_account = PlatformAccount.objects.create(
                    # Relationships
                    user=wa_account.owner,
                    
                    # Platform info
                    platform=PlatformAccount.PlatformType.WHATSAPP,
                    name=wa_account.name,
                    
                    # IDs
                    external_id=wa_account.phone_number_id,
                    parent_id=wa_account.waba_id,
                    
                    # Phone
                    phone_number=wa_account.phone_number,
                    display_phone_number=wa_account.display_phone_number or wa_account.phone_number,
                    
                    # Credentials
                    access_token_encrypted=wa_account.access_token_encrypted,
                    token_expires_at=wa_account.token_expires_at,
                    token_version=wa_account.token_version,
                    
                    # Webhook
                    webhook_verify_token=wa_account.webhook_verify_token,
                    
                    # Status
                    status=PlatformAccount.Status.ACTIVE if wa_account.status == 'active' else PlatformAccount.Status.PENDING,
                    is_active=wa_account.status == 'active',
                    is_verified=True,  # Already verified in WhatsApp
                    
                    # AI Agent
                    default_agent=wa_account.default_agent,
                    auto_response_enabled=wa_account.auto_response_enabled,
                    human_handoff_enabled=wa_account.human_handoff_enabled,
                    
                    # Metadata
                    metadata=wa_account.metadata or {},
                    
                    # Timestamps
                    created_at=wa_account.created_at,
                    updated_at=wa_account.updated_at,
                )
                
                # Add quality rating to metadata if available
                if hasattr(wa_account, 'quality_rating'):
                    platform_account.set_metadata('quality_rating', wa_account.quality_rating)
                
                logger.info(f"Migrated WhatsApp account: {wa_account.name} -> {platform_account.id}")
                migrated += 1
                
        except Exception as e:
            logger.error(f"Error migrating WhatsApp account {wa_account.id}: {e}")
            errors += 1
    
    logger.info(f"WhatsApp migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return migrated, skipped, errors


def migrate_instagram_accounts():
    """Migrate Instagram accounts to PlatformAccount."""
    from apps.instagram.models import InstagramAccount
    from apps.messaging.models import PlatformAccount
    
    logger.info("Starting Instagram account migration...")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for ig_account in InstagramAccount.objects.all():
        try:
            # Check if already migrated
            existing = PlatformAccount.objects.filter(
                platform=PlatformAccount.PlatformType.INSTAGRAM,
                external_id=ig_account.instagram_business_id or ig_account.id
            ).first()
            
            if existing:
                logger.info(f"Skipping already migrated Instagram account: {ig_account.username}")
                skipped += 1
                continue
            
            # Build metadata
            metadata = {
                'username': ig_account.username,
                'followers_count': ig_account.followers_count,
                'follows_count': ig_account.follows_count,
                'media_count': ig_account.media_count,
                'biography': ig_account.biography,
                'website': ig_account.website,
            }
            
            # Create unified account
            with transaction.atomic():
                platform_account = PlatformAccount.objects.create(
                    # Relationships
                    user=ig_account.user,
                    
                    # Platform info
                    platform=PlatformAccount.PlatformType.INSTAGRAM,
                    name=f"@{ig_account.username}",
                    
                    # IDs
                    external_id=ig_account.instagram_business_id or str(ig_account.id),
                    parent_id=ig_account.facebook_page_id or '',
                    
                    # Credentials
                    access_token_encrypted=ig_account.access_token,
                    token_expires_at=ig_account.token_expires_at,
                    
                    # Status
                    status=PlatformAccount.Status.ACTIVE if ig_account.is_active else PlatformAccount.Status.INACTIVE,
                    is_active=ig_account.is_active,
                    is_verified=ig_account.is_verified,
                    
                    # Metadata
                    metadata=metadata,
                    
                    # Timestamps
                    created_at=ig_account.created_at,
                    updated_at=ig_account.updated_at,
                    last_sync_at=ig_account.last_sync_at,
                )
                
                logger.info(f"Migrated Instagram account: {ig_account.username} -> {platform_account.id}")
                migrated += 1
                
        except Exception as e:
            logger.error(f"Error migrating Instagram account {ig_account.id}: {e}")
            errors += 1
    
    logger.info(f"Instagram migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return migrated, skipped, errors


def migrate_messenger_accounts():
    """Migrate Messenger accounts to PlatformAccount."""
    from apps.messaging.models import MessengerAccount
    from apps.messaging.models import PlatformAccount
    
    logger.info("Starting Messenger account migration...")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for ms_account in MessengerAccount.objects.all():
        try:
            # Check if already migrated
            existing = PlatformAccount.objects.filter(
                platform=PlatformAccount.PlatformType.MESSENGER,
                external_id=ms_account.page_id
            ).first()
            
            if existing:
                logger.info(f"Skipping already migrated Messenger account: {ms_account.page_name}")
                skipped += 1
                continue
            
            # Build metadata
            metadata = {
                'category': ms_account.category,
                'followers_count': ms_account.followers_count,
                'app_id': ms_account.app_id,
            }
            
            # Create unified account
            with transaction.atomic():
                platform_account = PlatformAccount.objects.create(
                    # Relationships
                    user=ms_account.user,
                    
                    # Platform info
                    platform=PlatformAccount.PlatformType.MESSENGER,
                    name=ms_account.page_name,
                    
                    # IDs
                    external_id=ms_account.page_id,
                    
                    # Credentials
                    access_token_encrypted=ms_account.page_access_token,
                    
                    # Webhook
                    webhook_verified=ms_account.webhook_verified,
                    
                    # Status
                    status=PlatformAccount.Status.ACTIVE if ms_account.is_active else PlatformAccount.Status.INACTIVE,
                    is_active=ms_account.is_active,
                    is_verified=True,
                    
                    # Metadata
                    metadata=metadata,
                    
                    # Timestamps
                    created_at=ms_account.created_at,
                    updated_at=ms_account.updated_at,
                    last_sync_at=ms_account.last_sync_at,
                )
                
                logger.info(f"Migrated Messenger account: {ms_account.page_name} -> {platform_account.id}")
                migrated += 1
                
        except Exception as e:
            logger.error(f"Error migrating Messenger account {ms_account.id}: {e}")
            errors += 1
    
    logger.info(f"Messenger migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return migrated, skipped, errors


def migrate_store_integrations():
    """Migrate StoreIntegration messaging accounts to PlatformAccount."""
    from apps.stores.models import StoreIntegration
    from apps.messaging.models import PlatformAccount
    
    logger.info("Starting StoreIntegration migration...")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    # Only migrate messaging platform integrations
    messaging_types = [
        StoreIntegration.IntegrationType.WHATSAPP,
        StoreIntegration.IntegrationType.INSTAGRAM,
        StoreIntegration.IntegrationType.FACEBOOK,
    ]
    
    for integration in StoreIntegration.objects.filter(integration_type__in=messaging_types):
        try:
            # Map integration type to platform
            platform_map = {
                StoreIntegration.IntegrationType.WHATSAPP: PlatformAccount.PlatformType.WHATSAPP,
                StoreIntegration.IntegrationType.INSTAGRAM: PlatformAccount.PlatformType.INSTAGRAM,
                StoreIntegration.IntegrationType.FACEBOOK: PlatformAccount.PlatformType.MESSENGER,
            }
            
            platform = platform_map.get(integration.integration_type)
            if not platform:
                continue
            
            # Determine external_id
            external_id = integration.external_id or integration.phone_number_id
            if not external_id:
                logger.info(f"Skipping StoreIntegration without external_id: {integration.id}")
                skipped += 1
                continue
            
            # Check if already migrated
            existing = PlatformAccount.objects.filter(
                platform=platform,
                external_id=external_id
            ).first()
            
            if existing:
                # Link to store if not already linked
                if integration.store and not existing.store:
                    existing.store = integration.store
                    existing.save(update_fields=['store'])
                    logger.info(f"Linked existing PlatformAccount to store: {existing.id}")
                skipped += 1
                continue
            
            # Map status
            status_map = {
                StoreIntegration.IntegrationStatus.ACTIVE: PlatformAccount.Status.ACTIVE,
                StoreIntegration.IntegrationStatus.INACTIVE: PlatformAccount.Status.INACTIVE,
                StoreIntegration.IntegrationStatus.ERROR: PlatformAccount.Status.ERROR,
                StoreIntegration.IntegrationStatus.PENDING: PlatformAccount.Status.PENDING,
            }
            
            # Create unified account
            with transaction.atomic():
                platform_account = PlatformAccount.objects.create(
                    # Relationships
                    user=integration.store.owner if integration.store else None,
                    store=integration.store,
                    
                    # Platform info
                    platform=platform,
                    name=integration.name,
                    
                    # IDs
                    external_id=external_id,
                    parent_id=integration.waba_id or '',
                    phone_number_id=integration.phone_number_id or '',
                    
                    # Credentials
                    access_token_encrypted=integration.access_token_encrypted,
                    token_expires_at=integration.token_expires_at,
                    
                    # Webhook
                    webhook_url=integration.webhook_url,
                    webhook_verify_token=integration.webhook_verify_token,
                    
                    # Status
                    status=status_map.get(integration.status, PlatformAccount.Status.PENDING),
                    is_active=integration.status == StoreIntegration.IntegrationStatus.ACTIVE,
                    
                    # Metadata
                    metadata=integration.metadata or {},
                    
                    # Timestamps
                    created_at=integration.created_at,
                    updated_at=integration.updated_at,
                )
                
                logger.info(f"Migrated StoreIntegration: {integration.name} -> {platform_account.id}")
                migrated += 1
                
        except Exception as e:
            logger.error(f"Error migrating StoreIntegration {integration.id}: {e}")
            errors += 1
    
    logger.info(f"StoreIntegration migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return migrated, skipped, errors


def run_migration():
    """Run all migrations."""
    logger.info("=" * 60)
    logger.info("Starting Platform Account Migration")
    logger.info("=" * 60)
    
    results = {
        'whatsapp': migrate_whatsapp_accounts(),
        'instagram': migrate_instagram_accounts(),
        'messenger': migrate_messenger_accounts(),
        'store_integrations': migrate_store_integrations(),
    }
    
    logger.info("=" * 60)
    logger.info("Migration Summary")
    logger.info("=" * 60)
    
    total_migrated = 0
    total_skipped = 0
    total_errors = 0
    
    for platform, (migrated, skipped, errors) in results.items():
        logger.info(f"{platform}: {migrated} migrated, {skipped} skipped, {errors} errors")
        total_migrated += migrated
        total_skipped += skipped
        total_errors += errors
    
    logger.info("-" * 60)
    logger.info(f"TOTAL: {total_migrated} migrated, {total_skipped} skipped, {total_errors} errors")
    logger.info("=" * 60)
    
    return results


# For Django-extensions runscript
def run(*args):
    """Entry point for Django runscript."""
    return run_migration()


if __name__ == '__main__':
    import os
    import sys
    import django
    
    # Setup Django
    sys.path.insert(0, '/home/graco/WORK/server')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    run_migration()
