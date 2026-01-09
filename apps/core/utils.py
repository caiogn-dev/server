"""
Core utilities and helper functions.
"""
import hmac
import hashlib
import secrets
from typing import Optional
from django.conf import settings
from cryptography.fernet import Fernet
import base64


def generate_token(length: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Meta webhook signature."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


class TokenEncryption:
    """Encrypt and decrypt sensitive tokens."""

    def __init__(self):
        key = settings.SECRET_KEY[:32].encode()
        key = base64.urlsafe_b64encode(key.ljust(32)[:32])
        self.cipher = Fernet(key)

    def encrypt(self, token: str) -> str:
        """Encrypt a token."""
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt a token."""
        return self.cipher.decrypt(encrypted_token.encode()).decode()


token_encryption = TokenEncryption()


def mask_token(token: str, visible_chars: int = 4) -> str:
    """Mask a token for display purposes."""
    if len(token) <= visible_chars * 2:
        return '*' * len(token)
    return f"{token[:visible_chars]}{'*' * (len(token) - visible_chars * 2)}{token[-visible_chars:]}"


def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to E.164 format."""
    phone = ''.join(filter(str.isdigit, phone))
    if not phone.startswith('55') and len(phone) <= 11:
        phone = '55' + phone
    return phone


def format_phone_for_display(phone: str) -> str:
    """Format phone number for display."""
    phone = normalize_phone_number(phone)
    if len(phone) == 13:
        return f"+{phone[:2]} ({phone[2:4]}) {phone[4:9]}-{phone[9:]}"
    elif len(phone) == 12:
        return f"+{phone[:2]} ({phone[2:4]}) {phone[4:8]}-{phone[8:]}"
    return phone


def generate_idempotency_key(*args) -> str:
    """Generate an idempotency key from arguments."""
    data = ':'.join(str(arg) for arg in args)
    return hashlib.sha256(data.encode()).hexdigest()
