#!/usr/bin/env python
"""
Debug completo: conversas e mensagens.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage
import requests
import json

print("=" * 80)
print("DEBUG: CONVERSAS E MENSAGENS DO INSTAGRAM")
print("=" * 80)

account = InstagramAccount.objects.filter(username='pastita.reserva').first()

if not account:
    print("❌ Conta não encontrada")
    sys.exit(1)

print(f"\n✅ Conta: {account.username}")
print(f"   Page ID: {account.facebook_page_id}")
print(f"   Instagram Business ID: {account.instagram_account_id}")

token = account.access_token

# 1. BUSCAR CONVERSAS DO BANCO
print("\n" + "=" * 80)
print("1. CONVERSAS NO BANCO DE DADOS")
print("=" * 80)

conversas = InstagramConversation.objects.filter(account=account).order_by('-last_message_at')
print(f"\nTotal: {conversas.count()}")

for conv in conversas:
    print(f"\n📝 Conversa: {conv.participant_name or conv.participant_username}")
    print(f"   ID: {conv.id}")
    print(f"   Participant ID: {conv.participant_id}")
    print(f"   Última mensagem: {conv.last_message_at}")
    print(f"   Preview: {conv.last_message_preview}")
    
    # Mensagens desta conversa
    msgs = InstagramMessage.objects.filter(conversation=conv).order_by('sent_at')
    print(f"   Mensagens no banco: {msgs.count()}")
    
    for msg in msgs[:5]:
        direction = "⬅️ Entrada" if msg.direction == 'inbound' else "➡️ Saída"
        print(f"     {direction}: {msg.text_content[:50] if msg.text_content else '(mídia)'}")

# 2. BUSCAR CONVERSAS DA API
print("\n" + "=" * 80)
print("2. CONVERSAS DA API DO INSTAGRAM")
print("=" * 80)

url = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}/conversations"
params = {
    'platform': 'instagram',
    'fields': 'id,participants,updated_time,messages{id,from,to,message,created_time}',
    'limit': 10,
    'access_token': token
}

try:
    resp = requests.get(url, params=params)
    print(f"\nStatus: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        conversas_api = data.get('data', [])
        print(f"Total de conversas na API: {len(conversas_api)}\n")
        
        for i, conv_data in enumerate(conversas_api, 1):
            print(f"\n📞 Conversa {i}:")
            print(f"   ID: {conv_data.get('id')}")
            print(f"   Atualizada: {conv_data.get('updated_time')}")
            
            # Participantes
            participants = conv_data.get('participants', {}).get('data', [])
            print(f"   Participantes: {len(participants)}")
            for p in participants:
                is_me = p.get('id') == account.instagram_account_id
                marker = "👤 (Você)" if is_me else "👥 (Cliente)"
                print(f"     {marker} ID: {p.get('id')}")
                print(f"        Username: {p.get('username', 'N/A')}")
                print(f"        Name: {p.get('name', 'N/A')}")
            
            # Mensagens
            messages = conv_data.get('messages', {}).get('data', [])
            print(f"   Mensagens na API: {len(messages)}")
            
            if messages:
                print(f"\n   📨 Últimas mensagens:")
                for msg in messages[:5]:
                    from_id = msg.get('from', {}).get('id')
                    to_id = msg.get('to', {}).get('data', [{}])[0].get('id')
                    is_from_me = from_id == account.instagram_account_id
                    direction = "➡️ Saída" if is_from_me else "⬅️ Entrada"
                    
                    print(f"     {direction} [{msg.get('created_time')}]")
                    print(f"        ID: {msg.get('id')}")
                    print(f"        From: {from_id}")
                    print(f"        To: {to_id}")
                    print(f"        Mensagem: {msg.get('message', '(vazio)')}")
            else:
                print(f"   ⚠️ Nenhuma mensagem retornada pela API!")
                print(f"   Isso pode significar que a conversa existe mas não tem mensagens acessíveis.")
    else:
        print(f"❌ Erro na API:")
        print(f"   {resp.text}")
except Exception as e:
    print(f"❌ Exceção: {e}")

# 3. TESTAR BUSCAR MENSAGENS DE UMA CONVERSA ESPECÍFICA
print("\n" + "=" * 80)
print("3. TESTANDO BUSCAR MENSAGENS DE CONVERSA ESPECÍFICA")
print("=" * 80)

conv_primeira = InstagramConversation.objects.filter(account=account).first()
if conv_primeira:
    print(f"\nTestando conversa: {conv_primeira.participant_name or conv_primeira.participant_username}")
    print(f"Participant ID: {conv_primeira.participant_id}")
    
    # Tentar buscar mensagens usando o participant_id
    url2 = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}/conversations"
    params2 = {
        'platform': 'instagram',
        'user_id': conv_primeira.participant_id,
        'fields': 'id,messages{id,from,to,message,created_time}',
        'access_token': token
    }
    
    try:
        resp2 = requests.get(url2, params=params2)
        print(f"\nStatus: {resp2.status_code}")
        
        if resp2.status_code == 200:
            data2 = resp2.json()
            print(f"Response: {json.dumps(data2, indent=2)}")
        else:
            print(f"❌ Erro: {resp2.text}")
    except Exception as e:
        print(f"❌ Exceção: {e}")
else:
    print("\n⚠️ Nenhuma conversa no banco para testar")

print("\n" + "=" * 80)
print("FIM DO DEBUG")
print("=" * 80)
