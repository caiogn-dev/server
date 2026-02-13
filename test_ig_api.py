import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

import django
django.setup()

import requests
from apps.instagram.models import InstagramAccount

acc = InstagramAccount.objects.first()
print(f'Page ID: {acc.facebook_page_id}')
print(f'Instagram ID: {acc.instagram_account_id}')

print()
print('=== Testando via Page ID ===')
r = requests.get(f'https://graph.facebook.com/v21.0/{acc.facebook_page_id}/conversations', params={
    'platform': 'instagram',
    'fields': 'participants,messages{id,message,from,created_time}',
    'access_token': acc.access_token
})
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Conversas encontradas: {len(data.get("data", []))}')
    for conv in data.get('data', []):
        print(f'  - {conv}')
else:
    print(f'Erro: {r.json()}')
