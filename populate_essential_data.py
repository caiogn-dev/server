"""
Script para popular o banco com dados essenciais extraídos.

Usage:
    python manage.py shell < populate_essential_data.py
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


def load_essential_data():
    """Load essential data from JSON file."""
    input_file = '/app/essential_data_backup.json'
    
    if not os.path.exists(input_file):
        logger.error(f"File not found: {input_file}")
        return None
    
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    return data


def populate_users(data):
    """Populate users table."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    logger.info("Populating users...")
    
    for user_data in data.get('users', []):
        try:
            User.objects.get_or_create(
                id=user_data['id'],
                defaults={
                    'username': user_data['username'],
                    'email': user_data['email'],
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                    'is_active': user_data.get('is_active', True),
                    'is_staff': user_data.get('is_staff', False),
                    'is_superuser': user_data.get('is_superuser', False),
                }
            )
        except Exception as e:
            logger.error(f"Failed to create user {user_data.get('id')}: {e}")
    
    logger.info(f"✅ Users populated")


def populate_stores(data):
    """Populate stores table."""
    from apps.commerce.models import Store
    
    logger.info("Populating stores...")
    
    for store_data in data.get('stores', []):
        try:
            Store.objects.get_or_create(
                id=store_data['id'],
                defaults={
                    'name': store_data['name'],
                    'slug': store_data['slug'],
                    'owner_id': store_data['owner_id'],
                    'business_name': store_data.get('business_name', store_data['name']),
                    'business_type': store_data.get('business_type', 'retail'),
                    'description': store_data.get('description', ''),
                    'phone': store_data.get('phone', ''),
                    'email': store_data.get('email', ''),
                    'address': store_data.get('address', ''),
                    'city': store_data.get('city', ''),
                    'state': store_data.get('state', ''),
                    'is_active': store_data.get('is_active', True),
                }
            )
        except Exception as e:
            logger.error(f"Failed to create store {store_data.get('id')}: {e}")
    
    logger.info(f"✅ Stores populated")


def populate_whatsapp_accounts(data):
    """Populate WhatsApp accounts."""
    from apps.messaging_v2.models import PlatformAccount
    
    logger.info("Populating WhatsApp accounts...")
    
    for account_data in data.get('whatsapp_accounts', []):
        try:
            PlatformAccount.objects.get_or_create(
                id=account_data['id'],
                defaults={
                    'platform': 'whatsapp',
                    'name': account_data['name'],
                    'phone_number': account_data['phone_number'],
                    'phone_number_id': account_data.get('phone_number_id', ''),
                    'business_account_id': account_data.get('business_account_id', ''),
                    'access_token': account_data.get('access_token', ''),
                    'is_active': account_data.get('is_active', True),
                    'is_verified': account_data.get('is_verified', False),
                    'store_id': account_data['store_id'],
                }
            )
        except Exception as e:
            logger.error(f"Failed to create WhatsApp account {account_data.get('id')}: {e}")
    
    logger.info(f"✅ WhatsApp accounts populated")


def populate_agents(data):
    """Populate agents."""
    from apps.agents.models import Agent
    
    logger.info("Populating agents...")
    
    for agent_data in data.get('agents', []):
        try:
            Agent.objects.get_or_create(
                id=agent_data['id'],
                defaults={
                    'name': agent_data['name'],
                    'description': agent_data.get('description', ''),
                    'store_id': agent_data['store_id'],
                    'is_active': agent_data.get('is_active', True),
                    'configuration': agent_data.get('configuration', {}),
                }
            )
        except Exception as e:
            logger.error(f"Failed to create agent {agent_data.get('id')}: {e}")
    
    logger.info(f"✅ Agents populated")


def populate_all():
    """Populate all essential data."""
    data = load_essential_data()
    
    if not data:
        logger.error("No data to populate")
        return
    
    try:
        with transaction.atomic():
            populate_users(data)
            populate_stores(data)
            populate_whatsapp_accounts(data)
            populate_agents(data)
        
        logger.info("=" * 60)
        logger.info("✅ ALL ESSENTIAL DATA POPULATED SUCCESSFULLY")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Failed to populate data: {e}")
        raise


if __name__ == '__main__':
    populate_all()
