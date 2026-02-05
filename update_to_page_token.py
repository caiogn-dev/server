#!/usr/bin/env python
"""
Buscar e salvar o Page Access Token correto.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
import requests

account = InstagramAccount.objects.filter(username='pastita.reserva').first()

if not account:
    print("❌ Conta não encontrada")
    sys.exit(1)

print(f"Conta: {account.username}")
print(f"Token atual (50 chars): {account.access_token[:50]}...")

# Buscar Page Access Token
url = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}"
params = {
    'fields': 'id,name,access_token',
    'access_token': account.access_token
}

try:
    resp = requests.get(url, params=params)
    
    if resp.status_code == 200:
        data = resp.json()
        page_token = data.get('access_token')
        
        if page_token:
            print(f"\n✅ Page Access Token encontrado!")
            print(f"   Token: {page_token[:50]}...")
            
            # Salvar no banco
            account.access_token = page_token
            account.save()
            
            print(f"\n✅ Token atualizado no banco!")
            print(f"   Token salvo (encriptado): {account._access_token[:50]}...")
        else:
            print(f"❌ Page Access Token não encontrado na resposta")
    else:
        print(f"❌ Erro ao buscar Page Access Token:")
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {resp.text}")
except Exception as e:
    print(f"❌ Erro: {e}")
