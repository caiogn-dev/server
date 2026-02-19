#!/usr/bin/env python
import django
django.setup()

from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount, Message
from apps.stores.models import StoreOrder, StoreCustomer
from django.contrib.auth import get_user_model
import datetime

print('='*60)
print('ESTATISTICAS DO SISTEMA - PASTITA 3D')
print('='*60)

User = get_user_model()
print(f"\nUSUARIOS: Total: {User.objects.count()}")

print(f"\nCLIENTES DA LOJA: Total: {StoreCustomer.objects.filter(is_active=True).count()}")

orders = StoreOrder.objects.filter(is_active=True)
today = datetime.date.today()
print(f"\nPEDIDOS:")
print(f"   Total: {orders.count()}")
print(f"   Hoje: {orders.filter(created_at__date=today).count()}")
print(f"   Pagos: {orders.filter(payment_status='paid').count()}")

print(f"\nCONVERSAS: Total: {Conversation.objects.count()}")
print(f"   Abertas: {Conversation.objects.filter(status='open').count()}")
print(f"   Fechadas: {Conversation.objects.filter(status='closed').count()}")

msgs = Message.objects.all()
print(f"\nMENSAGENS: Total: {msgs.count()}")
print(f"   Enviadas: {msgs.filter(direction='outgoing').count()}")
print(f"   Recebidas: {msgs.filter(direction='incoming').count()}")

print(f"\nWHATSAPP ACCOUNTS:")
for acc in WhatsAppAccount.objects.filter(is_active=True):
    print(f"   - {acc.name}: {acc.status} ({acc.phone_number or 'sem numero'})")

print('\n' + '='*60)
print('Sistema operacional!')
print('='*60)
