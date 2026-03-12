"""
Canonical resolver for Store, WhatsApp account and automation profile context.

This keeps Store as the business source of truth while CompanyProfile remains
the automation configuration layer linked to the store when available.
"""
from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount


@dataclass
class AutomationContext:
    store: Optional[Store] = None
    profile: Optional[CompanyProfile] = None
    account: Optional[WhatsAppAccount] = None
    conversation: Optional[Conversation] = None


class AutomationContextService:
    """Resolves the canonical automation context for messaging flows."""

    @staticmethod
    def _safe_related(obj, attr: str):
        try:
            return getattr(obj, attr)
        except ObjectDoesNotExist:
            return None

    @classmethod
    def resolve(
        cls,
        *,
        store: Optional[Store] = None,
        account: Optional[WhatsAppAccount] = None,
        company: Optional[CompanyProfile] = None,
        conversation: Optional[Conversation] = None,
        create_profile: bool = False,
    ) -> AutomationContext:
        if conversation is not None:
            account = account or conversation.account

        if company is not None:
            store = store or company.store
            account = account or company.account

        if store is not None and account is None:
            account = store.get_whatsapp_account()

        if account is not None and store is None:
            stores_manager = getattr(account, 'stores', None)
            if stores_manager is not None:
                store = stores_manager.filter(is_active=True).first() or stores_manager.first()

        profile = company
        if profile is None and store is not None:
            if create_profile:
                profile = store.get_automation_profile()
            else:
                profile = cls._safe_related(store, 'automation_profile')

        if profile is None and account is not None:
            profile = cls._safe_related(account, 'company_profile')

        if profile is not None:
            store = store or profile.store
            account = account or profile.account

        if store is not None and account is None:
            account = store.get_whatsapp_account()

        return AutomationContext(
            store=store,
            profile=profile,
            account=account,
            conversation=conversation,
        )
