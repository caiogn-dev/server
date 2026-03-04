"""
Django settings configuration for consolidated apps.

Add this to your main settings.py INSTALLED_APPS:

    # Core apps
    'apps.core_v2',
    'apps.commerce',
    'apps.messaging_v2',
    'apps.marketing_v2',
    
    # Legacy apps (to be removed after migration)
    # 'apps.users',
    # 'apps.audit',
    # 'apps.stores',
    # 'apps.whatsapp',
    # 'apps.instagram',
    # 'apps.messaging',
    # 'apps.conversations',
    # 'apps.handover',
    # 'apps.automation',
    # 'apps.campaigns',
    # 'apps.marketing',
    # 'apps.notifications',

"""

# Auth user model
AUTH_USER_MODEL = 'core_v2.User'

# Installed apps configuration
CONSOLIDATED_APPS = [
    # Core
    'apps.core_v2',
    
    # Business
    'apps.commerce',
    
    # Communication
    'apps.messaging_v2',
    'apps.marketing_v2',
    
    # Infrastructure
    'apps.webhooks',
    'apps.agents',
]

# Legacy apps (comment out after full migration)
LEGACY_APPS = [
    'apps.core',
    'apps.users',
    'apps.audit',
    'apps.stores',
    'apps.whatsapp',
    'apps.instagram',
    'apps.messaging',
    'apps.conversations',
    'apps.handover',
    'apps.automation',
    'apps.campaigns',
    'apps.marketing',
    'apps.notifications',
]

# URL Configuration
ROOT_URLCONF = 'config.urls'

# Database routing (optional - for gradual migration)
DATABASE_ROUTERS = []

# Migration settings
MIGRATION_MODULES = {
    # Map old apps to new ones during transition
    # 'stores': 'apps.commerce.migrations',
}
