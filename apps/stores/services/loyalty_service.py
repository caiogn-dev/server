"""Serviço de fidelidade persistida (multi-tenant, sem heurísticas hardcoded).

Regras de negócio (compre N itens qualificantes → ganhe 1):
- threshold por loja em store.metadata['loyalty_salads_required'] (default 10)
- enabled em store.metadata['loyalty_enabled'] (default True)
- categorias qualificantes em store.metadata['loyalty_qualifying_categories']
  (lista de category ids); vazio/ausente = TODO item qualifica
- rótulo do item em store.metadata['loyalty_item_label'] /
  'loyalty_item_label_plural' (default 'item'/'itens')
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
    def item_labels(store):
        """Rótulo do item qualificante, configurável por loja (default genérico)."""
        meta = store.metadata or {}
        singular = str(meta.get('loyalty_item_label') or 'item')
        plural = str(meta.get('loyalty_item_label_plural') or 'itens')
        return singular, plural

    @staticmethod
    def _get_account(store, user):
        account, _ = StoreLoyaltyAccount.objects.get_or_create(store=store, user=user)
        return account

    @staticmethod
    def _qualifying_categories(store):
        cats = (store.metadata or {}).get('loyalty_qualifying_categories') or []
        return {str(c).strip().lower() for c in cats if str(c).strip()}

    @staticmethod
    def _item_category_keys(item):
        """Chaves comparáveis da categoria do item: id, nome e slug (lowercase).

        Configs gravadas pelo painel usam ids, mas há metadata legada com
        NOMES de categoria (ex.: ['Saladas']) — aceitar ambos evita que a
        fidelidade pare de contar silenciosamente.
        """
        keys = set()
        cat_id = getattr(item, 'category_id', None)
        product = getattr(item, 'product', None)
        if not cat_id:
            cat_id = getattr(product, 'category_id', None)
        if cat_id:
            keys.add(str(cat_id).lower())
        category = getattr(item, 'category', None) or getattr(product, 'category', None)
        if category is not None:
            for attr in ('name', 'slug'):
                value = str(getattr(category, attr, '') or '').strip().lower()
                if value:
                    keys.add(value)
        return keys

    @staticmethod
    def _item_qualifies(store, item) -> bool:
        cats = LoyaltyService._qualifying_categories(store)
        if not cats:
            return True
        return bool(cats & LoyaltyService._item_category_keys(item))

    @staticmethod
    def order_item_qualifies(store, item) -> bool:
        return LoyaltyService._item_qualifies(store, item)

    @staticmethod
    def cart_item_qualifies(store, item) -> bool:
        return LoyaltyService._item_qualifies(store, item)

    @staticmethod
    def credit_order(order):
        """Credita os itens qualificados de um pedido (idempotente por pedido).

        Ponto único usado tanto pela mudança de status no painel quanto pela
        aprovação de pagamento via webhook/checkout.
        """
        if not order or not getattr(order, 'customer_id', None):
            return None
        store = order.store
        _, enabled = LoyaltyService._config(store)
        if not enabled:
            return None
        qty = sum(
            int(item.quantity or 0)
            for item in order.items.all()
            if LoyaltyService.order_item_qualifies(store, item)
        )
        if not qty:
            return None
        return LoyaltyService.credit_qualified(store, order.customer, order, qty)

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
