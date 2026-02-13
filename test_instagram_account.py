#!/usr/bin/env python
"""
Script para testar conta do Instagram e diagnosticar problemas.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPIService, InstagramAPIError


def test_account(account_id: str):
    """Testa uma conta do Instagram."""
    print(f"\n{'='*60}")
    print(f"TESTANDO CONTA: {account_id}")
    print(f"{'='*60}\n")
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
    except InstagramAccount.DoesNotExist:
        print(f"❌ Conta não encontrada: {account_id}")
        return
    
    print(f"✓ Nome: {account.name}")
    print(f"✓ Username: {account.username}")
    print(f"✓ Instagram Account ID: {account.instagram_account_id}")
    print(f"✓ Facebook Page ID: {account.facebook_page_id}")
    print(f"✓ Status: {account.status}")
    print(f"✓ Token Type: {'IGAA' if account.access_token.startswith('IGAA') else 'Page Access Token'}")
    print(f"✓ Token Masked: {account.masked_token}")
    
    api = InstagramAPIService(account)
    
    # Test 1: Get account info
    print(f"\n{'─'*60}")
    print("TEST 1: Get Account Info")
    print(f"{'─'*60}")
    try:
        info = api.get_account_info()
        print(f"✓ Account info retrieved successfully")
        print(f"  - Username: {info.get('username')}")
        print(f"  - Followers: {info.get('followers_count')}")
        print(f"  - Media Count: {info.get('media_count')}")
    except InstagramAPIError as e:
        print(f"❌ Failed to get account info: {e}")
        print(f"   Code: {e.code}, Subcode: {e.subcode}")
    
    # Test 2: Get conversations
    print(f"\n{'─'*60}")
    print("TEST 2: Get Conversations")
    print(f"{'─'*60}")
    try:
        convos = api.get_conversations(limit=5)
        print(f"✓ Conversations retrieved successfully")
        data = convos.get('data', [])
        print(f"  - Found {len(data)} conversations")
        for i, conv in enumerate(data[:3], 1):
            print(f"  {i}. ID: {conv.get('id')}")
    except InstagramAPIError as e:
        print(f"❌ Failed to get conversations: {e}")
        print(f"   Code: {e.code}, Subcode: {e.subcode}")
    
    # Test 3: Test sending message (dry run)
    print(f"\n{'─'*60}")
    print("TEST 3: Send Message Configuration")
    print(f"{'─'*60}")
    print(f"  Endpoint ID: {account.facebook_page_id or account.instagram_account_id}")
    print(f"  Using Facebook API: {bool(account.facebook_page_id)}")
    print(f"  Base URL: {api.base_url}")
    
    recipient_id = input("\nEnter recipient_id to test sending message (or press Enter to skip): ").strip()
    if recipient_id:
        test_message = input("Enter test message (or press Enter for 'Test'): ").strip() or "Test"
        print(f"\nAttempting to send: '{test_message}' to {recipient_id}...")
        try:
            result = api.send_text_message(recipient_id, test_message)
            print(f"✓ Message sent successfully!")
            print(f"  - Message ID: {result.get('message_id')}")
        except InstagramAPIError as e:
            print(f"❌ Failed to send message: {e}")
            print(f"   Code: {e.code}, Subcode: {e.subcode}")
    
    print(f"\n{'='*60}")
    print("TEST COMPLETED")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    # List all accounts
    accounts = InstagramAccount.objects.all()
    
    if not accounts:
        print("❌ Nenhuma conta do Instagram encontrada.")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print("CONTAS DISPONÍVEIS")
    print(f"{'='*60}\n")
    
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc.name} ({acc.username}) - ID: {acc.id}")
    
    print()
    
    if len(sys.argv) > 1:
        account_id = sys.argv[1]
    else:
        choice = input("Digite o número da conta para testar (ou ID direto): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            account_id = str(accounts[int(choice) - 1].id)
        else:
            account_id = choice
    
    test_account(account_id)
