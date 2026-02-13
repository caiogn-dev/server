import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

import django
django.setup()

from apps.instagram.models import InstagramAccount

acc = InstagramAccount.objects.first()
print(f'Page ID value: [{acc.facebook_page_id}]')
print(f'Page ID type: {type(acc.facebook_page_id)}')
print(f'Page ID bool: {bool(acc.facebook_page_id)}')
print(f'Instagram ID: [{acc.instagram_account_id}]')
