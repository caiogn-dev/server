#!/usr/bin/env python
"""Verificar detalhes do token atual"""
import requests

import os
token = os.environ.get('FACEBOOK_ACCESS_TOKEN', '')
if not token:
    raise SystemExit("Defina a variável de ambiente FACEBOOK_ACCESS_TOKEN antes de executar este script.")

print("\n" + "="*70)
print("DIAGNÓSTICO DO TOKEN")
print("="*70 + "\n")

# 1. Debug token
print("1️⃣  Verificando tipo e validade do token...\n")
response = requests.get(
    "https://graph.facebook.com/v21.0/debug_token",
    params={
        "input_token": token,
        "access_token": token
    }
)

if response.status_code == 200:
    data = response.json().get('data', {})
    print(f"✓ App ID: {data.get('app_id')}")
    print(f"✓ Tipo: {data.get('type')}")
    print(f"✓ Válido: {data.get('is_valid')}")
    print(f"✓ User ID: {data.get('user_id')}")
    print(f"✓ Expira em: {data.get('expires_at', 'Nunca')}")
    print(f"✓ Scopes: {', '.join(data.get('scopes', []))}")
else:
    print(f"❌ Erro: {response.json()}")

# 2. Check me endpoint
print("\n2️⃣  Verificando identidade do token...\n")
response = requests.get(
    "https://graph.facebook.com/v21.0/me",
    params={"access_token": token}
)

if response.status_code == 200:
    print(f"✓ {response.json()}")
else:
    print(f"❌ {response.json()}")

# 3. Try to get accounts
print("\n3️⃣  Tentando buscar páginas com este token...\n")
response = requests.get(
    "https://graph.facebook.com/v21.0/me/accounts",
    params={"access_token": token}
)

if response.status_code == 200:
    pages = response.json().get('data', [])
    if pages:
        print(f"✓ Encontradas {len(pages)} página(s):\n")
        for page in pages:
            print(f"  • {page['name']} (ID: {page['id']})")
            print(f"    Token: {page['access_token'][:30]}...")
            print(f"    Categoria: {page.get('category', 'N/A')}\n")
    else:
        print("❌ Nenhuma página encontrada")
else:
    print(f"❌ {response.json()}")

# 4. Try specific page
print("\n4️⃣  Tentando acessar a página 997369343457487...\n")
response = requests.get(
    "https://graph.facebook.com/v21.0/997369343457487",
    params={
        "access_token": token,
        "fields": "id,name,access_token"
    }
)

if response.status_code == 200:
    page_data = response.json()
    print(f"✓ Página: {page_data.get('name')}")
    if 'access_token' in page_data:
        print(f"✓ Page Access Token disponível: {page_data['access_token'][:30]}...")
        print(f"\n🎯 USE ESTE TOKEN:")
        print(f"{page_data['access_token']}")
    else:
        print("❌ Page Access Token NÃO disponível nesta resposta")
else:
    print(f"❌ {response.json()}")

print("\n" + "="*70)
print("\n💡 DIAGNÓSTICO:")
print("="*70)

# Try to send message with current token
print("\n5️⃣  Testando envio de mensagem com token atual...\n")
response = requests.post(
    "https://graph.facebook.com/v21.0/997369343457487/messages",
    json={
        "recipient": {"id": "1434322381572508"},
        "message": {"text": "Teste"}
    },
    params={"access_token": token}
)

if response.status_code == 200:
    print(f"✅ FUNCIONOU! {response.json()}")
else:
    error = response.json().get('error', {})
    print(f"❌ Erro {error.get('code')}: {error.get('message')}")
    
    if error.get('code') == 190:
        print("\n⚠️  PROBLEMA: Este token NÃO é um Page Access Token válido")
        print("SOLUÇÃO: Use o /me/accounts para pegar o Page Access Token correto")

print("\n")
