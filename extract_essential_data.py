"""
Script de extração de dados essenciais para migração completa.
Extrai: Lojas, WhatsApp Accounts e Agents

Usage:
    python manage.py shell < extract_essential_data.py
"""
import os
import sys
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')

import django
django.setup()

from django.db import connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_stores():
    """Extract all stores data."""
    logger.info("Extracting stores...")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, slug, owner_id, business_name, business_type,
                   description, phone, email, address, city, state,
                   is_active, created_at, updated_at
            FROM store_stores
        """)
        columns = [col[0] for col in cursor.description]
        stores = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    logger.info(f"Extracted {len(stores)} stores")
    return stores


def extract_whatsapp_accounts():
    """Extract all WhatsApp accounts."""
    logger.info("Extracting WhatsApp accounts...")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, phone_number, phone_number_id, business_account_id,
                   access_token, is_active, is_verified, store_id,
                   created_at, updated_at
            FROM whatsapp_accounts
        """)
        columns = [col[0] for col in cursor.description]
        accounts = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    logger.info(f"Extracted {len(accounts)} WhatsApp accounts")
    return accounts


def extract_agents():
    """Extract all agents."""
    logger.info("Extracting agents...")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, description, store_id, is_active,
                   configuration, created_at, updated_at
            FROM agents
        """)
        columns = [col[0] for col in cursor.description]
        agents = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    logger.info(f"Extracted {len(agents)} agents")
    return agents


def extract_users():
    """Extract all users."""
    logger.info("Extracting users...")
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, email, first_name, last_name,
                   is_active, is_staff, is_superuser, date_joined, last_login
            FROM auth_user
        """)
        columns = [col[0] for col in cursor.description]
        users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    logger.info(f"Extracted {len(users)} users")
    return users


def save_essential_data():
    """Save all essential data to JSON file."""
    data = {
        'stores': extract_stores(),
        'whatsapp_accounts': extract_whatsapp_accounts(),
        'agents': extract_agents(),
        'users': extract_users(),
    }
    
    output_file = '/app/essential_data_backup.json'
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    logger.info(f"✅ Essential data saved to {output_file}")
    logger.info(f"   - {len(data['stores'])} stores")
    logger.info(f"   - {len(data['whatsapp_accounts'])} WhatsApp accounts")
    logger.info(f"   - {len(data['agents'])} agents")
    logger.info(f"   - {len(data['users'])} users")
    
    return output_file


if __name__ == '__main__':
    save_essential_data()
