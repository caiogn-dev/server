#!/usr/bin/env python
import os, sys, django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount

# Read token from file
with open('/app/new_token.txt', 'r') as f:
    new_token = f.read().strip()

account = InstagramAccount.objects.first()
print(f"\n{'='*60}")
print("ATUALIZANDO TOKEN DO INSTAGRAM")
print(f"{'='*60}\n")
print(f"Conta: {account.username}")
print(f"Token antigo: {account.access_token[:30]}...")
print(f"Token novo: {new_token[:30]}...")

account.access_token = new_token
account.save()

print(f"\n✅ Token atualizado com sucesso!")
print(f"Token salvo (encriptado): {account.access_token_encrypted[:50]}...")
print(f"Token descriptografado: {account.access_token[:30]}...")
print(f"\n{'='*60}\n")
