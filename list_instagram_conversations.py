#!/usr/bin/env python
"""
Listar conversas do Instagram para pegar recipient_id válido.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage
from django.utils import timezone
from datetime import timedelta

# Buscar conta
account = InstagramAccount.objects.filter(username='pastita.reserva').first()

if not account:
    print("❌ Conta não encontrada")
    sys.exit(1)

print(f"Conta: {account.username}")
print(f"ID: {account.id}")
print(f"Page ID: {account.facebook_page_id}")
print(f"Instagram Business ID: {account.instagram_account_id}")
print("\n" + "=" * 80)

# Buscar conversas
conversas = InstagramConversation.objects.filter(account=account).order_by('-last_message_at')

print(f"\nTotal de conversas: {conversas.count()}")
print("\n" + "=" * 80)
print("CONVERSAS:")
print("=" * 80)

for conv in conversas[:10]:
    last_msg_time = conv.last_message_at
    if last_msg_time:
        hours_ago = (timezone.now() - last_msg_time).total_seconds() / 3600
        status = "✅ ATIVA (< 24h)" if hours_ago < 24 else f"❌ EXPIROU ({int(hours_ago)}h atrás)"
    else:
        status = "❓ Sem mensagens"
        hours_ago = 999
    
    print(f"\n{status}")
    print(f"  Participant ID: {conv.participant_id}")
    print(f"  Participant Name: {conv.participant_name}")
    print(f"  Última mensagem: {last_msg_time}")
    
    # Buscar última mensagem
    last_msg = InstagramMessage.objects.filter(conversation=conv).order_by('-sent_at').first()
    if last_msg:
        print(f"  Última msg: {last_msg.text_content[:50] if last_msg.text_content else '(mídia)'}...")
        print(f"  De: {'Cliente' if last_msg.direction == 'inbound' else 'Nós'}")

print("\n" + "=" * 80)
