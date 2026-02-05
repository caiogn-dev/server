#!/usr/bin/env python
"""Get Page Access Token from System User Token"""
import os, sys, django, requests
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount

account = InstagramAccount.objects.first()
system_user_token = account.access_token

print("\n" + "="*70)
print("CONVERTENDO SYSTEM USER TOKEN → PAGE ACCESS TOKEN")
print("="*70 + "\n")

print(f"System User Token: {system_user_token[:30]}...")

# Buscar Page Access Token usando o System User Token
response = requests.get(
    f"https://graph.facebook.com/v21.0/997369343457487",
    params={
        "access_token": system_user_token,
        "fields": "id,name,access_token"
    }
)

if response.status_code != 200:
    print(f"\n❌ Erro: {response.json()}")
    print("\n⚠️  O System User Token não tem acesso à página!")
    print("Verifique no Business Manager se o System User tem acesso à página Pastita Massas")
    sys.exit(1)

page_data = response.json()
page_access_token = page_data.get('access_token')

if not page_access_token:
    print(f"\n❌ Página encontrada mas sem access_token na resposta")
    print(f"Response: {page_data}")
    sys.exit(1)

print(f"\n✅ Página: {page_data['name']}")
print(f"✅ Page Access Token: {page_access_token[:30]}...")

# Testar o Page Access Token
print("\n" + "="*70)
print("TESTANDO PAGE ACCESS TOKEN")
print("="*70 + "\n")

test_response = requests.post(
    "https://graph.facebook.com/v21.0/997369343457487/messages",
    json={
        "recipient": {"id": "1434322381572508"},
        "message": {"text": "🎉 Token configurado com sucesso!"}
    },
    params={"access_token": page_access_token}
)

if test_response.status_code == 200:
    print(f"✅✅✅ MENSAGEM ENVIADA COM SUCESSO! ✅✅✅")
    print(f"Response: {test_response.json()}")
    
    # Salvar o Page Access Token
    account.access_token = page_access_token
    account.save()
    print(f"\n✅ Page Access Token salvo no banco de dados!")
    
else:
    error = test_response.json().get('error', {})
    print(f"❌ Erro {error.get('code')}: {error.get('message')}")
    print(f"\nMas vou salvar o token mesmo assim...")
    account.access_token = page_access_token
    account.save()
    print(f"✅ Page Access Token salvo!")

print("\n" + "="*70)
print("✅ CONCLUÍDO!")
print("="*70 + "\n")
