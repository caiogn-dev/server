# Migration: Consolidate CompanyProfile into Store
# This script migrates data from CompanyProfile to Store and establishes proper links

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/home/graco/WORK/server')
django.setup()

from apps.stores.models import Store
from apps.automation.models import CompanyProfile
from apps.whatsapp.models import WhatsAppAccount


def migrate_company_profiles():
    """
    Migrate CompanyProfile data to Store and establish proper links.
    """
    print("=" * 60)
    print("MIGRATION: CompanyProfile → Store")
    print("=" * 60)
    
    # Get all CompanyProfiles
    profiles = CompanyProfile.objects.all()
    print(f"\nFound {profiles.count()} CompanyProfiles")
    
    migrated = 0
    created = 0
    errors = 0
    
    for profile in profiles:
        try:
            print(f"\nProcessing CompanyProfile {profile.id}...")
            
            # Check if already linked to a Store
            if profile.store:
                print(f"  ✓ Already linked to Store {profile.store.id}")
                store = profile.store
            else:
                # Try to find existing Store by WhatsApp account
                if profile.account:
                    try:
                        # Look for store with same WhatsApp number
                        store = Store.objects.filter(
                            whatsapp_number=profile.account.phone_number
                        ).first()
                        
                        if store:
                            print(f"  ✓ Found existing Store {store.id} by WhatsApp number")
                            profile.store = store
                            profile.save()
                        else:
                            # Create new Store from CompanyProfile data
                            print(f"  → Creating new Store from CompanyProfile data...")
                            store = Store.objects.create(
                                name=profile._company_name or f"Store {profile.id}",
                                slug=f"store-{profile.id}",
                                description=profile._description or '',
                                phone=profile.account.phone_number if profile.account else '',
                                whatsapp_number=profile.account.phone_number if profile.account else '',
                                status='active' if profile.account and profile.account.is_active else 'pending',
                                store_type='food' if profile._business_type == 'restaurant' else 'other'
                            )
                            profile.store = store
                            profile.save()
                            created += 1
                            print(f"  ✓ Created Store {store.id}")
                    except Exception as e:
                        print(f"  ✗ Error finding/creating Store: {e}")
                        errors += 1
                        continue
                else:
                    print(f"  ✗ No account linked, skipping")
                    errors += 1
                    continue
            
            # Migrate data from CompanyProfile to Store if needed
            if not store.description and profile._description:
                store.description = profile._description
                store.save()
                print(f"  → Migrated description to Store")
            
            migrated += 1
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            errors += 1
    
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total CompanyProfiles: {profiles.count()}")
    print(f"Successfully linked: {migrated}")
    print(f"New Stores created: {created}")
    print(f"Errors: {errors}")
    print("=" * 60)


def verify_migration():
    """
    Verify that all CompanyProfiles are properly linked to Stores.
    """
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    
    unlinked = CompanyProfile.objects.filter(store__isnull=True).count()
    linked = CompanyProfile.objects.filter(store__isnull=False).count()
    
    print(f"Linked CompanyProfiles: {linked}")
    print(f"Unlinked CompanyProfiles: {unlinked}")
    
    if unlinked > 0:
        print("\n⚠️  WARNING: Some CompanyProfiles are still unlinked!")
        for profile in CompanyProfile.objects.filter(store__isnull=True):
            print(f"  - CompanyProfile {profile.id} (account: {profile.account})")
    else:
        print("\n✓ All CompanyProfiles are properly linked!")
    
    print("=" * 60)


if __name__ == '__main__':
    migrate_company_profiles()
    verify_migration()
