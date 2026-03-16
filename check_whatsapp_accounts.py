import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.whatsapp.models import WhatsAppAccount

accounts = WhatsAppAccount.objects.all()
print(f'Total WhatsApp Accounts: {accounts.count()}')

for acc in accounts[:5]:
    phone_id = getattr(acc, 'phone_number_id', 'NOT SET')
    status = getattr(acc, 'status', 'NOT SET')
    print(f'  Account ID: {acc.id}')
    print(f'    phone_number_id: {phone_id}')
    print(f'    status: {status}')
    print()

# Also check if there's a default account
from apps.whatsapp.utils import get_default_whatsapp_account
default_acc = get_default_whatsapp_account()
print(f'Default account: {default_acc}')
if default_acc:
    print(f'  phone_number_id: {default_acc.phone_number_id}')
