import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

import django
django.setup()

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPIService

acc = InstagramAccount.objects.first()
print(f'Page ID: {acc.facebook_page_id}')
print(f'Instagram ID: {acc.instagram_account_id}')
print()

api = InstagramAPIService(acc)
print(f'Base URL: {api.base_url}')
print()

print('=== Chamando get_conversations() ===')
try:
    result = api.get_conversations(limit=50)
    print(f'Sucesso! Encontradas: {len(result.get("data", []))} conversas')
    for c in result.get('data', []):
        print(f'  - ID: {c.get("id")}')
except Exception as e:
    print(f'ERRO: {type(e).__name__}: {e}')
