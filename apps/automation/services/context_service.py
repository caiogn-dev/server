"""
Canonical resolver for Store, WhatsApp account and automation profile context.

Store is the business source of truth.
CompanyProfile is the automation configuration layer attached to the store.
WhatsAppAccount is the transport/integration layer.
"""
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
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

    @staticmethod
    def _is_truthy(value) -> bool:
        return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

    @classmethod
    def _select_store_for_account(cls, account: Optional[WhatsAppAccount]) -> Optional[Store]:
        if account is None:
            return None

        stores_manager = getattr(account, 'stores', None)
        if stores_manager is None:
            return None

        return stores_manager.filter(is_active=True).first() or stores_manager.first()

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
            store = store or company.get_effective_store()
            account = account or company.get_effective_account()

        if store is not None and account is None:
            account = store.get_whatsapp_account()

        if account is not None and store is None:
            store = cls._select_store_for_account(account)

        profile = company
        if profile is None and store is not None:
            if create_profile:
                profile = store.get_automation_profile()
            else:
                profile = cls._safe_related(store, 'automation_profile')

        if profile is None and account is not None:
            profile = cls._safe_related(account, 'company_profile')

        if profile is not None:
            store = store or profile.get_effective_store()
            account = account or profile.get_effective_account()

        if store is not None and account is None:
            account = store.get_whatsapp_account()

        return AutomationContext(
            store=store,
            profile=profile,
            account=account,
            conversation=conversation,
        )

    @classmethod
    def sync_profile(
        cls,
        profile: Optional[CompanyProfile],
        *,
        save: bool = True,
    ) -> Optional[CompanyProfile]:
        if profile is None:
            return None

        update_fields = []
        store = profile.store or cls._select_store_for_account(profile.account)
        account = profile.account

        if store and not profile.store_id:
            profile.store = store
            update_fields.append('store')

        if store:
            store_account = store.get_whatsapp_account()
            if store_account and profile.account_id != store_account.id:
                profile.account = store_account
                update_fields.append('account')
            elif not store.whatsapp_account_id and account:
                store.whatsapp_account = account
                store.save(update_fields=['whatsapp_account', 'updated_at'])
        elif account and not profile.store_id:
            resolved_store = cls._select_store_for_account(account)
            if resolved_store:
                profile.store = resolved_store
                update_fields.append('store')

        if save and update_fields:
            profile.save(update_fields=list(dict.fromkeys(update_fields + ['updated_at'])))

        return profile

    @classmethod
    def get_default_agent(
        cls,
        *,
        context: Optional[AutomationContext] = None,
        store: Optional[Store] = None,
        account: Optional[WhatsAppAccount] = None,
        company: Optional[CompanyProfile] = None,
        conversation: Optional[Conversation] = None,
    ):
        context = context or cls.resolve(
            store=store,
            account=account,
            company=company,
            conversation=conversation,
            create_profile=False,
        )

        if context.profile is not None:
            agent = context.profile.get_default_agent()
            if agent is not None and agent.status == 'active':
                return agent

        if context.account is not None and getattr(context.account, 'default_agent_id', None):
            agent = context.account.default_agent
            if agent is not None and agent.status == 'active':
                return agent

        return None

    @classmethod
    def is_ai_enabled(
        cls,
        *,
        context: Optional[AutomationContext] = None,
        store: Optional[Store] = None,
        account: Optional[WhatsAppAccount] = None,
        company: Optional[CompanyProfile] = None,
        conversation: Optional[Conversation] = None,
        allow_env_override: bool = True,
    ) -> bool:
        context = context or cls.resolve(
            store=store,
            account=account,
            company=company,
            conversation=conversation,
            create_profile=False,
        )

        conversation = conversation or context.conversation
        if conversation is not None and getattr(conversation, 'mode', None) == 'human':
            return False

        if cls._is_truthy(getattr(settings, 'WHATSAPP_FORCE_DISABLE_LLM', 'false')):
            return False

        agent = cls.get_default_agent(context=context)
        if agent is None:
            return False

        if allow_env_override and cls._is_truthy(
            getattr(settings, 'WHATSAPP_ENABLE_LLM_FALLBACK', 'false')
        ):
            return True

        if context.profile is not None:
            return bool(context.profile.use_ai_agent)

        if context.account is not None:
            return bool(getattr(context.account, 'auto_response_enabled', False))

        return False
