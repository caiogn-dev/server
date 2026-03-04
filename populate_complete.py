"""
Popula dados completos no banco recriado (incluindo produtos e categorias).
"""
import os
import sys
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')

import django
django.setup()

from django.db import transaction
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def populate():
    # Load data
    with open('/app/complete_data.json', 'r') as f:
        data = json.load(f)
    
    from django.contrib.auth import get_user_model
    from apps.commerce.models import Store, Product, Category
    from apps.messaging_v2.models import PlatformAccount
    from apps.agents.models import Agent
    
    User = get_user_model()
    
    with transaction.atomic():
        # Users
        logger.info("Populating users...")
        for user_data in data.get('users', []):
            try:
                User.objects.get_or_create(
                    id=user_data['id'],
                    defaults={
                        'username': user_data['username'],
                        'email': user_data.get('email', ''),
                        'is_active': user_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"User error: {e}")
        
        # Stores
        logger.info("Populating stores...")
        for store_data in data.get('stores', []):
            try:
                Store.objects.get_or_create(
                    id=store_data['id'],
                    defaults={
                        'name': store_data['name'],
                        'slug': store_data.get('slug', store_data['name'].lower().replace(' ', '-')),
                        'is_active': store_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"Store error: {e}")
        
        # Categories
        logger.info("Populating categories...")
        for cat_data in data.get('categories', []):
            try:
                Category.objects.get_or_create(
                    id=cat_data['id'],
                    defaults={
                        'name': cat_data['name'],
                        'slug': cat_data.get('slug', cat_data['name'].lower().replace(' ', '-')),
                        'store_id': cat_data.get('store_id'),
                        'is_active': cat_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"Category error: {e}")
        
        # Products
        logger.info("Populating products...")
        for prod_data in data.get('products', []):
            try:
                Product.objects.get_or_create(
                    id=prod_data['id'],
                    defaults={
                        'name': prod_data['name'],
                        'slug': prod_data.get('slug', prod_data['name'].lower().replace(' ', '-')),
                        'description': prod_data.get('description', ''),
                        'price': prod_data.get('price', 0),
                        'cost_price': prod_data.get('cost_price', 0),
                        'stock_quantity': prod_data.get('stock_quantity', 0),
                        'sku': prod_data.get('sku', ''),
                        'store_id': prod_data.get('store_id'),
                        'category_id': prod_data.get('category_id'),
                        'is_active': prod_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"Product error: {e}")
        
        # WhatsApp Accounts
        logger.info("Populating WhatsApp accounts...")
        for account_data in data.get('whatsapp_accounts', []):
            try:
                PlatformAccount.objects.get_or_create(
                    id=account_data['id'],
                    defaults={
                        'platform': 'whatsapp',
                        'name': account_data.get('name', 'WhatsApp'),
                        'phone_number': account_data.get('phone_number', ''),
                        'is_active': account_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"WhatsApp error: {e}")
        
        # Agents
        logger.info("Populating agents...")
        for agent_data in data.get('agents', []):
            try:
                Agent.objects.get_or_create(
                    id=agent_data['id'],
                    defaults={
                        'name': agent_data['name'],
                        'is_active': agent_data.get('is_active', True),
                    }
                )
            except Exception as e:
                logger.error(f"Agent error: {e}")
    
    logger.info("✅ Dados completos populados!")
    logger.info(f"  - {len(data.get('stores', []))} stores")
    logger.info(f"  - {len(data.get('categories', []))} categories")
    logger.info(f"  - {len(data.get('products', []))} products")
    logger.info(f"  - {len(data.get('whatsapp_accounts', []))} WhatsApp accounts")
    logger.info(f"  - {len(data.get('agents', []))} agents")
    logger.info(f"  - {len(data.get('users', []))} users")


if __name__ == '__main__':
    populate()
