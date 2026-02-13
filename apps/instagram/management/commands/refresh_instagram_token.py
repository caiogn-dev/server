"""
Management command to refresh Instagram Page Access Token
"""
from django.core.management.base import BaseCommand
from apps.instagram.models import InstagramAccount
import requests
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh Instagram/Facebook Page Access Tokens before they expire'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=str,
            help='Instagram Account ID to refresh (default: all accounts)',
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        
        if account_id:
            accounts = InstagramAccount.objects.filter(id=account_id)
        else:
            accounts = InstagramAccount.objects.filter(status='active')
        
        self.stdout.write(f"\n{'='*70}")
        self.stdout.write("INSTAGRAM TOKEN REFRESH")
        self.stdout.write(f"{'='*70}\n")
        
        for account in accounts:
            self.stdout.write(f"\nProcessing: {account.username} (ID: {account.id})")
            
            if not account.app_id or not account.app_secret:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Skipping {account.username}: App ID/Secret not configured"
                ))
                continue
            
            try:
                # Exchange current token for a new long-lived token
                response = requests.get(
                    "https://graph.facebook.com/v21.0/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": account.app_id,
                        "client_secret": account.app_secret,
                        "fb_exchange_token": account.access_token
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    error = response.json().get('error', {})
                    self.stdout.write(self.style.ERROR(
                        f"❌ Error refreshing token: {error.get('message', 'Unknown error')}"
                    ))
                    continue
                
                data = response.json()
                new_token = data.get('access_token')
                expires_in = data.get('expires_in', 'Unknown')
                
                if new_token:
                    account.access_token = new_token
                    account.save()
                    
                    days = int(expires_in) // 86400 if expires_in != 'Unknown' else 'Unknown'
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ Token refreshed successfully! Expires in ~{days} days"
                    ))
                    
                    logger.info(f"Instagram token refreshed for account {account.id}", extra={
                        'account_id': account.id,
                        'username': account.username,
                        'expires_in_days': days
                    })
                else:
                    self.stdout.write(self.style.ERROR("❌ No token in response"))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Exception: {str(e)}"))
                logger.error(f"Error refreshing Instagram token: {e}", exc_info=True, extra={
                    'account_id': account.id
                })
        
        self.stdout.write(f"\n{'='*70}\n")
        self.stdout.write(self.style.SUCCESS("✅ Token refresh completed"))
