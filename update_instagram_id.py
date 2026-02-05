#!/usr/bin/env python
"""
Atualizar Instagram Business Account ID.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount

account = InstagramAccount.objects.filter(username='user_25933691062929660').first()

if account:
    print(f"Atualizando conta {account.username}")
    print(f"ID antigo: {account.instagram_account_id}")
    print(f"ID novo: 17841480118684547")
    print(f"Username novo: pastita.reserva")
    
    account.instagram_account_id = '17841480118684547'
    account.username = 'pastita.reserva'
    account.save()
    
    print(f"✅ Conta atualizada com sucesso!")
else:
    print("❌ Conta não encontrada")
