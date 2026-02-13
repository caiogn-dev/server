#!/usr/bin/env python
"""
Teste DIRETO na API do Graph do Facebook - Sem passar pelo código da app.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
import requests
import json

print("=" * 80)
print("TESTE DIRETO NA API DO GRAPH DO FACEBOOK")
print("=" * 80)

account = InstagramAccount.objects.filter(username='pastita.reserva').first()

if not account:
    print("❌ Conta não encontrada")
    sys.exit(1)

token = account.access_token
page_id = account.facebook_page_id
instagram_id = account.instagram_account_id

print(f"\n📋 DADOS:")
print(f"   Page ID: {page_id}")
print(f"   Instagram ID: {instagram_id}")
print(f"   Token: {token[:50]}...")

print("\n" + "=" * 80)
print("TESTE 1: Informações da Página")
print("=" * 80)

url1 = f"https://graph.facebook.com/v21.0/{page_id}"
params1 = {
    'fields': 'id,name,instagram_business_account{id,username}',
    'access_token': token
}

resp1 = requests.get(url1, params=params1)
print(f"\n🌐 URL: {url1}")
print(f"📊 Status: {resp1.status_code}")
print(f"📄 Response:")
print(json.dumps(resp1.json(), indent=2))

print("\n" + "=" * 80)
print("TESTE 2: Tentativa de Envio de Mensagem")
print("=" * 80)

recipient_id = "1434322381572508"  # gracolandi4
url2 = f"https://graph.facebook.com/v21.0/{page_id}/messages"

payload = {
    'recipient': {'id': recipient_id},
    'message': {'text': '🧪 Teste direto da API do Graph'}
}

headers = {'Content-Type': 'application/json'}
params2 = {'access_token': token}

print(f"\n🌐 URL: {url2}")
print(f"📦 Payload:")
print(json.dumps(payload, indent=2))

resp2 = requests.post(url2, json=payload, params=params2, headers=headers)
print(f"\n📊 Status: {resp2.status_code}")
print(f"📄 Response:")
print(json.dumps(resp2.json(), indent=2))

if resp2.status_code == 200:
    print("\n✅ SUCESSO! Mensagem enviada!")
    print(f"   Message ID: {resp2.json().get('message_id', 'N/A')}")
else:
    error = resp2.json().get('error', {})
    print(f"\n❌ ERRO!")
    print(f"   Código: {error.get('code')}")
    print(f"   Tipo: {error.get('type')}")
    print(f"   Mensagem: {error.get('message')}")
    print(f"   FBTrace ID: {error.get('fbtrace_id')}")
    
    # Link de debug
    fbtrace = error.get('fbtrace_id')
    if fbtrace:
        print(f"\n🔍 DEBUG no Facebook:")
        print(f"   https://developers.facebook.com/tools/debug/accesstoken/?access_token={token[:30]}...")
        print(f"   https://www.meta.com/debug/?mid={error.get('error-mid', 'N/A')}")

print("\n" + "=" * 80)
print("TESTE 3: Usando CURL (copie e cole no terminal)")
print("=" * 80)

curl_cmd = f'''curl -X POST "https://graph.facebook.com/v21.0/{page_id}/messages" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "recipient": {{"id": "{recipient_id}"}},
    "message": {{"text": "Teste via CURL"}}
  }}' \\
  "?access_token={token}"'''

print(f"\n{curl_cmd}")

print("\n" + "=" * 80)
print("TESTE 4: Verificar Permissões do Token")
print("=" * 80)

url3 = f"https://graph.facebook.com/v21.0/debug_token"
params3 = {
    'input_token': token,
    'access_token': token
}

resp3 = requests.get(url3, params=params3)
print(f"\n📊 Status: {resp3.status_code}")
if resp3.status_code == 200:
    data3 = resp3.json().get('data', {})
    print(f"\n📋 Informações do Token:")
    print(f"   App ID: {data3.get('app_id')}")
    print(f"   Tipo: {data3.get('type')}")
    print(f"   Válido: {data3.get('is_valid')}")
    print(f"   Expira em: {data3.get('expires_at', 'Nunca')}")
    print(f"   User ID: {data3.get('user_id')}")
    
    scopes = data3.get('scopes', [])
    print(f"\n🔐 Permissões (Scopes): {len(scopes)}")
    for scope in sorted(scopes):
        print(f"   - {scope}")
else:
    print(f"❌ Erro: {resp3.text}")

print("\n" + "=" * 80)
