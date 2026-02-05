#!/usr/bin/env python
"""
Executar sync de conversas manualmente com debug.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage
from apps.instagram.services.instagram_api import InstagramAPIService
from dateutil.parser import parse as parse_datetime

account = InstagramAccount.objects.filter(username='pastita.reserva').first()

if not account:
    print("❌ Conta não encontrada")
    sys.exit(1)

print(f"Conta: {account.username}")
print(f"=" * 80)

api = InstagramAPIService(account)
data = api.get_conversations(limit=50)

conversations_data = data.get('data', [])
print(f"\nConversas encontradas: {len(conversations_data)}")

synced = 0
errors = 0

for conv_data in conversations_data:
    try:
        # Get participant info
        participants = conv_data.get('participants', {}).get('data', [])
        participant = None
        for p in participants:
            if p.get('id') != account.instagram_account_id:
                participant = p
                break
        
        if not participant:
            print(f"⚠️ Conversa sem participante válido, pulando...")
            continue
        
        participant_id = participant.get('id', '')
        print(f"\n📝 Processando conversa com {participant.get('username', participant_id)}")
        
        # Create or update conversation
        conversation, created = InstagramConversation.objects.update_or_create(
            account=account,
            participant_id=participant_id,
            defaults={
                'participant_username': participant.get('username', ''),
                'participant_name': participant.get('name', participant.get('username', '')),
                'participant_profile_pic': participant.get('profile_pic', ''),
                'status': InstagramConversation.ConversationStatus.ACTIVE,
            }
        )
        print(f"   Conversa {'criada' if created else 'atualizada'}: {conversation.id}")
        
        # Sync messages from this conversation
        messages_data = conv_data.get('messages', {}).get('data', [])
        print(f"   Mensagens para processar: {len(messages_data)}")
        
        for i, msg_data in enumerate(messages_data, 1):
            try:
                msg_from = msg_data.get('from', {})
                msg_to = msg_data.get('to', {}).get('data', [{}])[0] if msg_data.get('to') else {}
                
                is_outbound = msg_from.get('id') == account.instagram_account_id
                direction = 'outbound' if is_outbound else 'inbound'
                
                msg_id = msg_data.get('id', '')
                created_time = msg_data.get('created_time')
                
                print(f"   [{i}] {direction}: {msg_data.get('message', '(vazio)')[:30]}...")
                print(f"       ID: {msg_id[:30]}...")
                print(f"       Time: {created_time}")
                
                message, msg_created = InstagramMessage.objects.update_or_create(
                    account=account,
                    instagram_message_id=msg_id,
                    defaults={
                        'conversation': conversation,
                        'direction': direction,
                        'message_type': 'text',
                        'status': 'delivered',
                        'sender_id': msg_from.get('id', ''),
                        'recipient_id': msg_to.get('id', '') if msg_to else participant_id,
                        'text_content': msg_data.get('message', ''),
                        'sent_at': parse_datetime(created_time) if created_time else None,
                    }
                )
                print(f"       Mensagem {'criada' if msg_created else 'atualizada'} no banco")
                
            except Exception as e:
                print(f"       ❌ Erro ao salvar mensagem: {e}")
                import traceback
                traceback.print_exc()
                errors += 1
        
        # Update conversation stats
        conversation.message_count = conversation.messages.count()
        last_msg = conversation.messages.order_by('-sent_at').first()
        if last_msg:
            conversation.last_message_at = last_msg.sent_at
            conversation.last_message_preview = last_msg.text_content[:100] if last_msg.text_content else ''
        conversation.save()
        
        print(f"   ✅ Conversa sincronizada: {conversation.message_count} mensagens")
        synced += 1
        
    except Exception as e:
        print(f"❌ Erro ao processar conversa: {e}")
        import traceback
        traceback.print_exc()
        errors += 1

print(f"\n" + "=" * 80)
print(f"✅ Sincronizadas: {synced} conversas")
print(f"❌ Erros: {errors}")
