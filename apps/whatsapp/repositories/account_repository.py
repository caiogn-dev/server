"""
WhatsApp Account Repository.
"""
from typing import Optional, List
from uuid import UUID
from django.db.models import QuerySet
from ..models import WhatsAppAccount


class WhatsAppAccountRepository:
    """Repository for WhatsApp Account operations."""

    def get_by_id(self, account_id: UUID) -> Optional[WhatsAppAccount]:
        """Get account by ID."""
        try:
            return WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return None

    def get_by_phone_number_id(self, phone_number_id: str) -> Optional[WhatsAppAccount]:
        """Get account by phone number ID."""
        try:
            return WhatsAppAccount.objects.get(
                phone_number_id=phone_number_id,
                is_active=True
            )
        except WhatsAppAccount.DoesNotExist:
            return None

    def get_by_phone_number(self, phone_number: str) -> Optional[WhatsAppAccount]:
        """Get account by phone number."""
        try:
            return WhatsAppAccount.objects.get(
                phone_number=phone_number,
                is_active=True
            )
        except WhatsAppAccount.DoesNotExist:
            return None

    def get_all_active(self) -> QuerySet[WhatsAppAccount]:
        """Get all active accounts."""
        return WhatsAppAccount.objects.filter(
            is_active=True,
            status=WhatsAppAccount.AccountStatus.ACTIVE
        )

    def get_by_owner(self, owner_id: int) -> QuerySet[WhatsAppAccount]:
        """Get accounts by owner."""
        return WhatsAppAccount.objects.filter(
            owner_id=owner_id,
            is_active=True
        )

    def create(self, **kwargs) -> WhatsAppAccount:
        """Create a new account."""
        access_token = kwargs.pop('access_token', None)
        account = WhatsAppAccount(**kwargs)
        if access_token:
            account.access_token = access_token
        account.save()
        return account

    def update(self, account: WhatsAppAccount, **kwargs) -> WhatsAppAccount:
        """Update an account."""
        access_token = kwargs.pop('access_token', None)
        for key, value in kwargs.items():
            setattr(account, key, value)
        if access_token:
            account.access_token = access_token
        account.save()
        return account

    def delete(self, account: WhatsAppAccount) -> None:
        """Soft delete an account."""
        account.is_active = False
        account.status = WhatsAppAccount.AccountStatus.INACTIVE
        account.save(update_fields=['is_active', 'status', 'updated_at'])

    def hard_delete(self, account: WhatsAppAccount) -> None:
        """Hard delete an account."""
        account.delete()

    def activate(self, account: WhatsAppAccount) -> WhatsAppAccount:
        """Activate an account."""
        account.status = WhatsAppAccount.AccountStatus.ACTIVE
        account.save(update_fields=['status', 'updated_at'])
        return account

    def deactivate(self, account: WhatsAppAccount) -> WhatsAppAccount:
        """Deactivate an account."""
        account.status = WhatsAppAccount.AccountStatus.INACTIVE
        account.save(update_fields=['status', 'updated_at'])
        return account

    def exists_by_phone_number_id(self, phone_number_id: str) -> bool:
        """Check if account exists by phone number ID."""
        return WhatsAppAccount.objects.filter(
            phone_number_id=phone_number_id
        ).exists()
