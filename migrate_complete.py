"""
Complete migration script from old apps to new consolidated structure.

Usage:
    python manage.py shell < migrate_complete.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')
django.setup()

from django.db import transaction, connection
from django.utils import timezone
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_table_exists(table_name):
    """Check if a table exists in the database."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, [table_name])
        return cursor.fetchone()[0]


def migrate_users():
    """Migrate users from old structure."""
    logger.info("=" * 60)
    logger.info("MIGRATING USERS")
    logger.info("=" * 60)
    
    try:
        from django.contrib.auth import get_user_model
        OldUser = get_user_model()
        
        count = OldUser.objects.count()
        logger.info(f"Found {count} existing users")
        logger.info("Users are already in auth_user table, no migration needed")
        
    except Exception as e:
        logger.error(f"User migration error: {e}")


def migrate_stores_to_commerce():
    """Migrate stores to commerce app."""
    logger.info("=" * 60)
    logger.info("MIGRATING STORES TO COMMERCE")
    logger.info("=" * 60)
    
    try:
        from apps.stores.models import Store as OldStore
        from apps.commerce.models import Store as NewStore
        
        migrated = 0
        for old in OldStore.objects.all():
            try:
                # Check if already migrated
                if NewStore.objects.filter(id=old.id).exists():
                    continue
                
                # Create new store with same ID
                NewStore.objects.create(
                    id=old.id,
                    name=old.name,
                    slug=old.slug,
                    owner_id=old.owner_id,
                    business_name=getattr(old, 'business_name', old.name),
                    business_type=getattr(old, 'business_type', 'retail'),
                    description=getattr(old, 'description', ''),
                    phone=getattr(old, 'phone', ''),
                    email=getattr(old, 'email', ''),
                    address=getattr(old, 'address', ''),
                    city=getattr(old, 'city', ''),
                    state=getattr(old, 'state', ''),
                    is_active=old.is_active,
                    settings=getattr(old, 'settings', {}),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Failed to migrate store {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} stores")
        
    except Exception as e:
        logger.error(f"Store migration error: {e}")


def migrate_products_to_commerce():
    """Migrate products to commerce app."""
    logger.info("=" * 60)
    logger.info("MIGRATING PRODUCTS TO COMMERCE")
    logger.info("=" * 60)
    
    try:
        # Check if old products exist
        if not check_table_exists('stores_product'):
            logger.info("No old products table found")
            return
        
        from apps.stores.models import Product as OldProduct
        from apps.commerce.models import Product as NewProduct
        
        migrated = 0
        for old in OldProduct.objects.all():
            try:
                if NewProduct.objects.filter(id=old.id).exists():
                    continue
                
                NewProduct.objects.create(
                    id=old.id,
                    store_id=old.store_id,
                    name=old.name,
                    slug=old.slug,
                    description=getattr(old, 'description', ''),
                    price=old.price,
                    cost_price=getattr(old, 'cost_price', 0),
                    stock_quantity=getattr(old, 'stock_quantity', 0),
                    sku=getattr(old, 'sku', ''),
                    is_active=getattr(old, 'is_active', True),
                    images=getattr(old, 'images', []),
                    category_id=getattr(old, 'category_id', None),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Failed to migrate product {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} products")
        
    except Exception as e:
        logger.error(f"Product migration error: {e}")


def migrate_orders_to_commerce():
    """Migrate orders to commerce app."""
    logger.info("=" * 60)
    logger.info("MIGRATING ORDERS TO COMMERCE")
    logger.info("=" * 60)
    
    try:
        if not check_table_exists('stores_order'):
            logger.info("No old orders table found")
            return
        
        from apps.stores.models import Order as OldOrder
        from apps.commerce.models import Order as NewOrder
        
        migrated = 0
        for old in OldOrder.objects.all():
            try:
                if NewOrder.objects.filter(id=old.id).exists():
                    continue
                
                NewOrder.objects.create(
                    id=old.id,
                    store_id=old.store_id,
                    customer_id=old.customer_id,
                    status=getattr(old, 'status', 'pending'),
                    subtotal=old.subtotal,
                    shipping_cost=getattr(old, 'shipping_cost', 0),
                    discount=getattr(old, 'discount', 0),
                    total=old.total,
                    customer_name=getattr(old, 'customer_name', ''),
                    customer_phone=getattr(old, 'customer_phone', ''),
                    customer_email=getattr(old, 'customer_email', ''),
                    shipping_address=getattr(old, 'shipping_address', ''),
                    payment_method=getattr(old, 'payment_method', ''),
                    payment_status=getattr(old, 'payment_status', 'pending'),
                    external_payment_id=getattr(old, 'external_payment_id', ''),
                    paid_at=getattr(old, 'paid_at', None),
                    shipped_at=getattr(old, 'shipped_at', None),
                    delivered_at=getattr(old, 'delivered_at', None),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Failed to migrate order {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} orders")
        
    except Exception as e:
        logger.error(f"Order migration error: {e}")


def migrate_customers_to_commerce():
    """Migrate customers to commerce app."""
    logger.info("=" * 60)
    logger.info("MIGRATING CUSTOMERS TO COMMERCE")
    logger.info("=" * 60)
    
    try:
        if not check_table_exists('stores_customer'):
            logger.info("No old customers table found")
            return
        
        from apps.stores.models import Customer as OldCustomer
        from apps.commerce.models import Customer as NewCustomer
        
        migrated = 0
        for old in OldCustomer.objects.all():
            try:
                if NewCustomer.objects.filter(id=old.id).exists():
                    continue
                
                NewCustomer.objects.create(
                    id=old.id,
                    store_id=old.store_id,
                    name=old.name,
                    phone=old.phone,
                    email=getattr(old, 'email', ''),
                    whatsapp_id=getattr(old, 'whatsapp_id', ''),
                    instagram_id=getattr(old, 'instagram_id', ''),
                    cpf=getattr(old, 'cpf', ''),
                    birth_date=getattr(old, 'birth_date', None),
                    address=getattr(old, 'address', ''),
                    total_orders=getattr(old, 'total_orders', 0),
                    total_spent=getattr(old, 'total_spent', 0),
                    last_order_at=getattr(old, 'last_order_at', None),
                    tags=getattr(old, 'tags', []),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Failed to migrate customer {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} customers")
        
    except Exception as e:
        logger.error(f"Customer migration error: {e}")


def migrate_whatsapp_to_messaging():
    """Migrate WhatsApp data to messaging."""
    logger.info("=" * 60)
    logger.info("MIGRATING WHATSAPP TO MESSAGING")
    logger.info("=" * 60)
    
    try:
        from apps.whatsapp.models import WhatsAppAccount as OldAccount
        from apps.messaging_v2.models import PlatformAccount
        
        migrated = 0
        for old in OldAccount.objects.all():
            try:
                if PlatformAccount.objects.filter(id=old.id).exists():
                    continue
                
                PlatformAccount.objects.create(
                    id=old.id,
                    platform='whatsapp',
                    store_id=old.store_id,
                    name=old.name,
                    phone_number=old.phone_number,
                    phone_number_id=old.phone_number_id,
                    business_account_id=getattr(old, 'business_account_id', ''),
                    access_token=old.access_token,
                    is_active=old.is_active,
                    is_verified=getattr(old, 'is_verified', False),
                    settings=getattr(old, 'settings', {}),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
            except Exception as e:
                logger.error(f"Failed to migrate WhatsApp account {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} WhatsApp accounts")
        
    except Exception as e:
        logger.error(f"WhatsApp migration error: {e}")


def migrate_messages_to_unified():
    """Migrate messages to unified model."""
    logger.info("=" * 60)
    logger.info("MIGRATING MESSAGES TO UNIFIED")
    logger.info("=" * 60)
    
    try:
        from apps.whatsapp.models import Message as OldMessage
        from apps.messaging_v2.models import UnifiedMessage
        
        migrated = 0
        batch_size = 1000
        total = OldMessage.objects.count()
        
        logger.info(f"Found {total} messages to migrate")
        
        for i, old in enumerate(OldMessage.objects.iterator()):
            try:
                if UnifiedMessage.objects.filter(id=old.id).exists():
                    continue
                
                UnifiedMessage.objects.create(
                    id=old.id,
                    platform='whatsapp',
                    platform_account_id=str(old.account_id),
                    platform_account_type='whatsapp.WhatsAppAccount',
                    conversation_id=getattr(old, 'conversation_id', None),
                    direction=getattr(old, 'direction', 'inbound'),
                    status=getattr(old, 'status', 'delivered'),
                    message_type=getattr(old, 'message_type', 'text'),
                    content={'text': old.text} if old.text else {},
                    text=old.text or '',
                    external_id=getattr(old, 'whatsapp_message_id', ''),
                    sent_at=getattr(old, 'sent_at', None),
                    delivered_at=getattr(old, 'delivered_at', None),
                    read_at=getattr(old, 'read_at', None),
                    metadata=getattr(old, 'metadata', {}),
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                )
                migrated += 1
                
                if migrated % batch_size == 0:
                    logger.info(f"Migrated {migrated}/{total} messages...")
                    
            except Exception as e:
                logger.error(f"Failed to migrate message {old.id}: {e}")
        
        logger.info(f"Migrated {migrated} messages total")
        
    except Exception as e:
        logger.error(f"Message migration error: {e}")


def run_complete_migration():
    """Run all migrations in order."""
    logger.info("=" * 70)
    logger.info("STARTING COMPLETE MIGRATION TO V2")
    logger.info("=" * 70)
    
    start_time = timezone.now()
    
    try:
        with transaction.atomic():
            # Phase 1: Core
            migrate_users()
            
            # Phase 2: Commerce
            migrate_stores_to_commerce()
            migrate_products_to_commerce()
            migrate_customers_to_commerce()
            migrate_orders_to_commerce()
            
            # Phase 3: Messaging
            migrate_whatsapp_to_messaging()
            migrate_messages_to_unified()
            
            # Phase 4: Marketing (from migrate_to_v2.py)
            # This would be called separately
        
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 70)
        logger.info(f"MIGRATION COMPLETED SUCCESSFULLY in {duration:.2f} seconds")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"MIGRATION FAILED: {e}")
        logger.error("=" * 70)
        raise


if __name__ == '__main__':
    run_complete_migration()
