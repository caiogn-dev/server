"""
Script para migrar dados dos apps legados para messaging_v2.

Uso:
    docker exec pastita_web python manage.py shell < migrate_to_messaging_v2.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()

# Models de destino (messaging_v2)
from apps.messaging_v2.models import PlatformAccount, Conversation, UnifiedMessage

# Models de origem
from apps.whatsapp.models import WhatsAppAccount
from apps.messaging.models import MessengerAccount
from apps.instagram.models import InstagramAccount


def migrate_whatsapp_accounts():
    """Migrar contas do WhatsApp."""
    print("Migrando contas do WhatsApp...")
    
    migrated = 0
    skipped = 0
    
    for wa_account in WhatsAppAccount.objects.all():
        # Verificar se já existe
        existing = PlatformAccount.objects.filter(
            user=wa_account.user,
            platform='whatsapp',
            phone_number_id=wa_account.phone_number_id
        ).first()
        
        if existing:
            print(f"  ⚠️  Conta WhatsApp {wa_account.name} já existe, pulando...")
            skipped += 1
            continue
        
        # Criar nova conta
        PlatformAccount.objects.create(
            created_by=wa_account.user,
            platform='whatsapp',
            name=wa_account.name,
            phone_number_id=wa_account.phone_number_id,
            waba_id=wa_account.waba_id,
            phone_number=wa_account.phone_number,
            display_phone_number=wa_account.display_phone_number,
            access_token=wa_account.access_token_encrypted,  # Note: está criptografado
            status='active' if wa_account.status == 'active' else 'pending',
            is_active=wa_account.status == 'active',
            is_verified=True,
            webhook_verified=True,
            auto_response_enabled=wa_account.auto_response_enabled,
            human_handoff_enabled=wa_account.human_handoff_enabled,
            default_agent_id=wa_account.default_agent_id if wa_account.default_agent else None,
        )
        migrated += 1
        print(f"  ✅ Migrada: {wa_account.name}")
    
    print(f"WhatsApp: {migrated} migradas, {skipped} puladas")
    return migrated, skipped


def migrate_messenger_accounts():
    """Migrar contas do Messenger."""
    print("\nMigrando contas do Messenger...")
    
    migrated = 0
    skipped = 0
    
    for ms_account in MessengerAccount.objects.all():
        # Verificar se já existe
        existing = PlatformAccount.objects.filter(
            user=ms_account.user,
            platform='messenger',
            page_id=ms_account.page_id
        ).first()
        
        if existing:
            print(f"  ⚠️  Conta Messenger {ms_account.page_name} já existe, pulando...")
            skipped += 1
            continue
        
        # Criar nova conta
        PlatformAccount.objects.create(
            created_by=ms_account.user,
            platform='messenger',
            name=ms_account.page_name,
            page_id=ms_account.page_id,
            page_name=ms_account.page_name,
            page_access_token=ms_account.page_access_token,
            app_id=ms_account.app_id,
            app_secret=ms_account.app_secret,
            status='active' if ms_account.is_active else 'inactive',
            is_active=ms_account.is_active,
            is_verified=ms_account.webhook_verified,
            webhook_verified=ms_account.webhook_verified,
            category=ms_account.category,
            followers_count=ms_account.followers_count,
        )
        migrated += 1
        print(f"  ✅ Migrada: {ms_account.page_name}")
    
    print(f"Messenger: {migrated} migradas, {skipped} puladas")
    return migrated, skipped


def migrate_instagram_accounts():
    """Migrar contas do Instagram."""
    print("\nMigrando contas do Instagram...")
    
    migrated = 0
    skipped = 0
    
    for ig_account in InstagramAccount.objects.all():
        # Verificar se já existe
        existing = PlatformAccount.objects.filter(
            user=ig_account.user,
            platform='instagram',
            instagram_account_id=ig_account.instagram_id
        ).first()
        
        if existing:
            print(f"  ⚠️  Conta Instagram {ig_account.username} já existe, pulando...")
            skipped += 1
            continue
        
        # Criar nova conta
        PlatformAccount.objects.create(
            created_by=ig_account.user,
            platform='instagram',
            name=ig_account.username or ig_account.instagram_id,
            instagram_account_id=ig_account.instagram_id,
            access_token=ig_account.access_token,
            status='active' if ig_account.is_active else 'inactive',
            is_active=ig_account.is_active,
            is_verified=ig_account.is_verified,
        )
        migrated += 1
        print(f"  ✅ Migrada: {ig_account.username or ig_account.instagram_id}")
    
    print(f"Instagram: {migrated} migradas, {skipped} puladas")
    return migrated, skipped


def main():
    """Executar migração completa."""
    print("=" * 60)
    print("MIGRAÇÃO PARA MESSAGING_V2")
    print("=" * 60)
    
    try:
        with transaction.atomic():
            wa_migrated, wa_skipped = migrate_whatsapp_accounts()
            ms_migrated, ms_skipped = migrate_messenger_accounts()
            ig_migrated, ig_skipped = migrate_instagram_accounts()
            
            total_migrated = wa_migrated + ms_migrated + ig_migrated
            total_skipped = wa_skipped + ms_skipped + ig_skipped
            
            print("\n" + "=" * 60)
            print("RESUMO DA MIGRAÇÃO")
            print("=" * 60)
            print(f"Total migrado: {total_migrated}")
            print(f"Total pulado (já existia): {total_skipped}")
            print("\n✅ Migração concluída com sucesso!")
            
    except Exception as e:
        print(f"\n❌ Erro na migração: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
