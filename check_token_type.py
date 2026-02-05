#!/usr/bin/env python
"""
Verificar tipo e validade do token.
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
print(f"Page ID: {account.facebook_page_id}")
print(f"Instagram Business ID: {account.instagram_account_id}")

token = account.access_token
print(f"\n✅ Token (50 chars): {token[:50]}...")

# Verificar tipo do token
print("\n" + "=" * 80)
print("TESTANDO TIPO DO TOKEN")
print("=" * 80)

# 1. Tentar buscar info do token usando debug_token
app_id = "YOUR_APP_ID"  # Você precisa fornecer isso
app_secret = "YOUR_APP_SECRET"  # Você precisa fornecer isso

# 2. Tentar buscar conversas com Page ID
print("\nTentando buscar conversas com Page ID...")
url = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}/conversations"
params = {
    'platform': 'instagram',
    'limit': 5,
    'access_token': token
}

try:
    resp = requests.get(url, params=params)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Sucesso! Encontradas {len(data.get('data', []))} conversas")
        print(f"Response: {data}")
    else:
        print(f"❌ Erro: {resp.text}")
        error_data = resp.json()
        error = error_data.get('error', {})
        print(f"\nCódigo de erro: {error.get('code')}")
        print(f"Mensagem: {error.get('message')}")
        
        if error.get('code') == 190:
            print("\n💡 ERRO 190: Token inválido ou expirado!")
            print("   Você precisa gerar um novo Page Access Token.")
except Exception as e:
    print(f"❌ Exceção: {e}")

# 3. Verificar se podemos acessar a página
print("\n" + "=" * 80)
print("TESTANDO ACESSO À PÁGINA")
print("=" * 80)

url2 = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}"
params2 = {
    'fields': 'id,name,access_token',
    'access_token': token
}

try:
    resp2 = requests.get(url2, params=params2)
    print(f"Status: {resp2.status_code}")
    
    if resp2.status_code == 200:
        data2 = resp2.json()
        print(f"✅ Página: {data2.get('name')}")
        print(f"   ID: {data2.get('id')}")
        
        # Se retornar access_token, significa que o token atual tem permissão para buscar o token da página
        if 'access_token' in data2:
            print(f"   ⚠️ Este token PODE buscar um Page Access Token, mas NÃO É um Page Access Token!")
            print(f"   Page Access Token disponível: {data2['access_token'][:50]}...")
    else:
        print(f"❌ Erro: {resp2.text}")
except Exception as e:
    print(f"❌ Exceção: {e}")

print("\n" + "=" * 80)
