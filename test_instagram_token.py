#!/usr/bin/env python
import os, sys, django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
import requests

account = InstagramAccount.objects.first()
print(f"\n{'='*60}")
print(f"TESTE DO NOVO TOKEN")
print(f"{'='*60}\n")
print(f"Username: {account.username}")
print(f"Page ID: {account.facebook_page_id}")
print(f"Instagram ID: {account.instagram_account_id}")
print(f"Token: {account.access_token[:30]}...\n")

# Test 1: Get page info
print("Teste 1: Acessar informações da página...")
response = requests.get(
    f'https://graph.facebook.com/v21.0/{account.facebook_page_id}',
    params={'access_token': account.access_token, 'fields': 'id,name'},
    timeout=10
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ Sucesso: {response.json()}")
else:
    print(f"❌ Erro: {response.json()}")

# Test 2: Try to send a test message
print("\nTeste 2: Tentar enviar mensagem de teste...")
test_recipient = "1434322381572508"
response = requests.post(
    f'https://graph.facebook.com/v21.0/{account.facebook_page_id}/messages',
    json={'recipient': {'id': test_recipient}, 'message': {'text': 'Teste do novo token'}},
    params={'access_token': account.access_token},
    timeout=10
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ MENSAGEM ENVIADA! {response.json()}")
else:
    print(f"❌ Erro: {response.json()}")

print(f"\n{'='*60}\n")
