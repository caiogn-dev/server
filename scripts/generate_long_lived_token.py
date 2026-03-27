#!/usr/bin/env python
"""
Script para gerar Long-Lived Page Access Token do Instagram/Facebook
"""
import requests
import sys

print("\n" + "="*70)
print("GERADOR DE LONG-LIVED PAGE ACCESS TOKEN")
print("="*70 + "\n")

# Configurações
APP_ID = input("Digite o Facebook App ID: ").strip()
APP_SECRET = input("Digite o Facebook App Secret: ").strip()
SHORT_LIVED_USER_TOKEN = input("Digite o User Access Token (do Graph Explorer): ").strip()

print("\n1️⃣  Trocando User Token curto por Long-Lived User Token (60 dias)...")

# Passo 1: Trocar por Long-Lived User Token
response = requests.get(
    "https://graph.facebook.com/v21.0/oauth/access_token",
    params={
        "grant_type": "fb_exchange_token",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": SHORT_LIVED_USER_TOKEN
    }
)

if response.status_code != 200:
    print(f"❌ Erro: {response.json()}")
    sys.exit(1)

long_lived_user_token = response.json()["access_token"]
expires_in = response.json().get("expires_in", "Unknown")
print(f"✅ Long-Lived User Token gerado! (Expira em {expires_in} segundos = ~{int(expires_in)//86400} dias)")

print("\n2️⃣  Buscando Long-Lived Page Access Token...")

# Passo 2: Pegar Long-Lived Page Token
response = requests.get(
    "https://graph.facebook.com/v21.0/me/accounts",
    params={"access_token": long_lived_user_token}
)

if response.status_code != 200:
    print(f"❌ Erro: {response.json()}")
    sys.exit(1)

pages = response.json().get("data", [])

if not pages:
    print("❌ Nenhuma página encontrada para este usuário")
    sys.exit(1)

print(f"\n✅ {len(pages)} página(s) encontrada(s):\n")

for i, page in enumerate(pages, 1):
    print(f"{i}. {page['name']} (ID: {page['id']})")

if len(pages) == 1:
    selected_page = pages[0]
else:
    choice = int(input(f"\nEscolha a página (1-{len(pages)}): "))
    selected_page = pages[choice - 1]

page_access_token = selected_page["access_token"]
page_id = selected_page["id"]
page_name = selected_page["name"]

print(f"\n" + "="*70)
print("✅ LONG-LIVED PAGE ACCESS TOKEN GERADO COM SUCESSO!")
print("="*70 + "\n")
print(f"Página: {page_name}")
print(f"Page ID: {page_id}")
print(f"Token: {page_access_token[:30]}...")
print(f"\nToken completo:\n{page_access_token}\n")
print("="*70)
print("\nCOMANDOS PARA ATUALIZAR NO DJANGO:")
print("="*70 + "\n")
print("docker-compose -f docker-compose.cloudflared.yml exec web python manage.py shell\n")
print("from apps.instagram.models import InstagramAccount")
print("account = InstagramAccount.objects.first()")
print(f"account.access_token = '{page_access_token}'")
print(f"account.facebook_page_id = '{page_id}'")
print("account.save()")
print("print('✅ Token atualizado!')")
print("\n" + "="*70 + "\n")

# Salvar em arquivo
with open("long_lived_page_token.txt", "w") as f:
    f.write(page_access_token)
print("💾 Token salvo em: long_lived_page_token.txt\n")
