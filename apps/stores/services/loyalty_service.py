"""Serviço de fidelidade persistida.

Regras de negócio iguais ao programa atual (compre N saladas → ganhe 1):
- threshold por loja em store.metadata['loyalty_salads_required'] (default 10)
- enabled em store.metadata['loyalty_enabled'] (default True)
"""
import logging

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.stores.models import StoreLoyaltyAccount, StoreLoyaltyTransaction

logger = logging.getLogger(__name__)


class LoyaltyService:
    @staticmethod
    def _config(store):
        meta = store.metadata or {}
        threshold = max(1, int(meta.get('loyalty_salads_required', 10) or 10))
        enabled = bool(meta.get('loyalty_enabled', True))
        return threshold, enabled

    @staticmethod
    def _get_account(store, user):
        account, _ = StoreLoyaltyAccount.objects.get_or_create(store=store, user=user)
        return account

    @staticmethod
    def _qualifying_categories(store):
        cats = (store.metadata or {}).get('loyalty_qualifying_categories') or []
        return {str(c) for c in cats}

    @staticmethod
    def _item_category_id(item):
        cat = getattr(item, 'category_id', None)
        if cat:
            return cat
        product = getattr(item, 'product', None)
        return getattr(product, 'category_id', None)

    @staticmethod
    def order_item_qualifies(store, item) -> bool:
        from apps.stores.services.checkout_service import CheckoutService
        cats = LoyaltyService._qualifying_categories(store)
        if cats:
            return str(LoyaltyService._item_category_id(item)) in cats
        return CheckoutService._is_salad_order_item(item)

    @staticmethod
    def cart_item_qualifies(store, item) -> bool:
        from apps.stores.services.checkout_service import CheckoutService
        cats = LoyaltyService._qualifying_categories(store)
        if cats:
            return str(LoyaltyService._item_category_id(item)) in cats
        return CheckoutService._is_salad_cart_item(item)

    @staticmethod
    @transaction.atomic
    def credit_qualified(store, user, order, quantity: int):
        """Credita itens qualificados de um pedido. Idempotente por pedido."""
        if not user or not quantity:
            return None
        account = LoyaltyService._get_account(store, user)
        try:
            tx = StoreLoyaltyTransaction.objects.create(
                account=account,
                order=order,
                kind=StoreLoyaltyTransaction.Kind.EARN,
                quantity=quantity,
            )
        except IntegrityError:
            # Pedido já creditado — idempotência via unique(order, kind)
            return None
        StoreLoyaltyAccount.objects.filter(id=account.id).update(
            qualified_count=F('qualified_count') + quantity,
        )
        return tx

    @staticmethod
    @transaction.atomic
    def redeem(store, user, order, rewards: int = 1):
        """Registra resgate de recompensa. Levanta ValueError sem saldo."""
        threshold, _ = LoyaltyService._config(store)
        account = LoyaltyService._get_account(store, user)
        account = StoreLoyaltyAccount.objects.select_for_update().get(id=account.id)
        earned = account.qualified_count // threshold
        available = earned - account.redeemed_count
        if rewards > available:
            raise ValueError(
                f'Saldo de fidelidade insuficiente: disponível {available}, pedido {rewards}.'
            )
        tx = StoreLoyaltyTransaction.objects.create(
            account=account,
            order=order,
            kind=StoreLoyaltyTransaction.Kind.REDEEM,
            quantity=rewards,
        )
        StoreLoyaltyAccount.objects.filter(id=account.id).update(
            redeemed_count=F('redeemed_count') + rewards,
        )
        return tx

    @staticmethod
    @transaction.atomic
    def backfill_redeemed(store, user, rewards: int):
        """Migração do histórico legado: registra resgates antigos sem checagem de saldo."""
        if not rewards:
            return None
        account = LoyaltyService._get_account(store, user)
        tx = StoreLoyaltyTransaction.objects.create(
            account=account,
            order=None,
            kind=StoreLoyaltyTransaction.Kind.REDEEM,
            quantity=rewards,
            note='backfill histórico legado',
        )
        StoreLoyaltyAccount.objects.filter(id=account.id).update(
            redeemed_count=F('redeemed_count') + rewards,
        )
        return tx

    @staticmethod
    def get_status(store, user) -> dict:
        """Status no mesmo formato do CheckoutService.get_loyalty_status."""
        threshold, enabled = LoyaltyService._config(store)

        empty = {
            'enabled': enabled,
            'threshold': threshold,
            'qualified_salads': 0,
            'rewards_earned': 0,
            'rewards_redeemed': 0,
            'available_rewards': 0,
            'progress': 0,
            'remaining': threshold,
            'can_redeem': False,
        }
        if not user or not getattr(user, 'is_authenticated', True):
            return empty
        account = StoreLoyaltyAccount.objects.filter(store=store, user=user).first()
        if not account:
            return empty

        qualified = account.qualified_count
        earned = qualified // threshold
        available = max(0, earned - account.redeemed_count)
        progress = qualified % threshold
        return {
            'enabled': enabled,
            'threshold': threshold,
            'qualified_salads': qualified,
            'rewards_earned': earned,
            'rewards_redeemed': account.redeemed_count,
            'available_rewards': available,
            'progress': progress,
            'remaining': threshold - progress,
            'can_redeem': enabled and available > 0,
        }
