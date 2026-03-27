"""
Custom Django model fields for the Pastita Platform.
"""
import logging
from django.db import models
from cryptography.fernet import InvalidToken

logger = logging.getLogger(__name__)


class EncryptedCharField(models.CharField):
    """
    CharField that transparently encrypts values at rest using Fernet (AES-128-CBC).

    - Encryption key derived from settings.SECRET_KEY via TokenEncryption.
    - Existing plaintext values in the DB are returned as-is on read and
      re-encrypted on the next save, enabling a smooth zero-downtime migration.
    - Encrypted ciphertext is ~40% longer than plaintext; max_length should
      account for this.  The default (1000) comfortably fits a 500-char secret.

    Usage::

        api_key = EncryptedCharField(max_length=1000, blank=True)
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 1000)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        return self._decrypt(value)

    def get_prep_value(self, value):
        if not value:
            return value
        return self._encrypt(value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cipher():
        from apps.core.utils import token_encryption
        return token_encryption

    def _encrypt(self, value: str) -> str:
        """Encrypt *value* if it is not already a Fernet token."""
        if not value:
            return value
        # Avoid double-encrypting values that came back from the DB.
        if self._looks_encrypted(value):
            return value
        try:
            return self._get_cipher().encrypt(value)
        except Exception:
            logger.exception("EncryptedCharField: encryption failed")
            return value

    def _decrypt(self, value: str) -> str:
        """Decrypt *value*.  Falls back to the raw value for legacy plaintext."""
        if not value:
            return value
        if not self._looks_encrypted(value):
            return value
        try:
            return self._get_cipher().decrypt(value)
        except (InvalidToken, Exception):
            # Value was not encrypted (legacy row) — return as-is.
            return value

    @staticmethod
    def _looks_encrypted(value: str) -> bool:
        """Heuristic: Fernet tokens start with 'gAAA' (base64 of \x80\x02)."""
        return isinstance(value, str) and value.startswith('gAAA')

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Keep max_length in migration so the column is wide enough.
        return name, path, args, kwargs
