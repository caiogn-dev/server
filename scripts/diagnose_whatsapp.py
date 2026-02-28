"""
Diagnostic script for WhatsApp messaging issues
Run this to identify why messages are not being received or sent
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/home/graco/WORK/server')
django.setup()

from django.db import connection
from apps.whatsapp.models import WhatsAppAccount, Message, WebhookEvent
from apps.automation.models import CompanyProfile

print("=" * 60)
print("WHATSAPP MESSAGING DIAGNOSTIC")
print("=" * 60)

# 1. Check WhatsApp Accounts
print("\n1. WHATSAPP ACCOUNTS STATUS")
print("-" * 40)
accounts = WhatsAppAccount.objects.all()
print(f"Total accounts: {accounts.count()}")

for account in accounts:
    print(f"\n  Account: {account.phone_number}")
    print(f"    ID: {account.id}")
    print(f"    Status: {'Active' if account.is_active else 'Inactive'}")
    print(f"    Connected: {account.is_connected}")
    print(f"    Webhook Configured: {bool(account.webhook_verify_token)}")
    print(f"    API Token: {'Set' if account.api_token else 'NOT SET'}")
    
    # Check company profile
    try:
        profile = CompanyProfile.objects.get(account=account)
        print(f"    Auto Reply: {'Enabled' if profile.auto_reply_enabled else 'Disabled'}")
        print(f"    LLM Enabled: {profile.llm_enabled if hasattr(profile, 'llm_enabled') else 'N/A'}")
    except CompanyProfile.DoesNotExist:
        print(f"    Company Profile: NOT FOUND")

# 2. Recent Messages
print("\n\n2. RECENT MESSAGES (Last 24 hours)")
print("-" * 40)
from datetime import datetime, timedelta
from django.utils import timezone

cutoff = timezone.now() - timedelta(hours=24)
messages = Message.objects.filter(created_at__gte=cutoff).order_by('-created_at')[:10]

print(f"Total messages in last 24h: {Message.objects.filter(created_at__gte=cutoff).count()}")
print(f"\nLast 10 messages:")
for msg in messages:
    direction = "📩 IN" if msg.direction == 'inbound' else "📤 OUT"
    status = msg.status
    print(f"  {direction} | {msg.created_at.strftime('%H:%M')} | {status} | {msg.content[:50]}")

# 3. Recent Webhook Events
print("\n\n3. RECENT WEBHOOK EVENTS (Last 24 hours)")
print("-" * 40)
webhook_events = WebhookEvent.objects.filter(created_at__gte=cutoff).order_by('-created_at')[:10]

print(f"Total webhook events in last 24h: {WebhookEvent.objects.filter(created_at__gte=cutoff).count()}")
print(f"\nLast 10 events:")
for event in webhook_events:
    status_icon = "✅" if event.processing_status == 'completed' else "⏳" if event.processing_status == 'pending' else "❌"
    print(f"  {status_icon} | {event.created_at.strftime('%H:%M')} | {event.event_type} | {event.processing_status}")

# 4. Pending Messages
print("\n\n4. PENDING MESSAGES")
print("-" * 40)
pending = Message.objects.filter(status='pending').count()
print(f"Pending messages: {pending}")

# 5. Failed Messages
print("\n\n5. FAILED MESSAGES (Last 24 hours)")
print("-" * 40)
failed = Message.objects.filter(status='failed', created_at__gte=cutoff).count()
print(f"Failed messages: {failed}")

if failed > 0:
    failed_msgs = Message.objects.filter(status='failed', created_at__gte=cutoff)[:5]
    for msg in failed_msgs:
        print(f"  - {msg.to_number}: {msg.error_message[:100] if msg.error_message else 'No error message'}")

# 6. Database Queries
print("\n\n6. DATABASE CONNECTION")
print("-" * 40)
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        print("  Database connection: OK")
except Exception as e:
    print(f"  Database connection: FAILED - {e}")

# 7. Celery Status Check
print("\n\n7. CELERY STATUS")
print("-" * 40)
try:
    from celery import current_app
    inspector = current_app.control.inspect()
    active = inspector.active()
    scheduled = inspector.scheduled()
    
    if active is None:
        print("  Celery workers: NOT RUNNING (or not reachable)")
    else:
        print(f"  Active workers: {len(active) if active else 0}")
        print(f"  Scheduled tasks: {len(scheduled) if scheduled else 0}")
except Exception as e:
    print(f"  Celery status: UNKNOWN - {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)

print("\nCOMMON ISSUES:")
print("-" * 40)
print("1. If Celery is not running, messages won't be sent asynchronously")
print("2. If WhatsApp account is not active, webhooks won't be received")
print("3. If CompanyProfile.auto_reply_enabled is True, handlers respond automatically")
print("4. Check WHATSAPP_WEBHOOK_VERIFY_TOKEN in settings")

