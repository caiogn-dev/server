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
    def _product_loyalty_units(item):
        """Multiplicador explícito do produto (attributes['loyalty_units']).

        Ex.: "Combo Tilápia" = 1 produto com 4 saladas → loyalty_units: 4.
        Retorna None quando ausente/inválido/<=0 (cai na regra de categoria).
        """
        product = getattr(item, 'product', None)
        attrs = getattr(product, 'attributes', None) or {}
        try:
            units = int(attrs.get('loyalty_units'))
        except (TypeError, ValueError):
            return None
        return units if units > 0 else None

    @staticmethod
    def item_qualified_units(store, item) -> int:
        """Selos que este item do pedido/carrinho vale.

        `loyalty_units` no produto é opt-in explícito: qualifica mesmo fora
        das categorias configuradas e multiplica pela quantidade. Sem ele,
        vale a regra de categoria (1 selo por unidade).
        """
        quantity = int(getattr(item, 'quantity', 0) or 0)
        if not quantity:
            return 0
        units = LoyaltyService._product_loyalty_units(item)
        if units is not None:
            return quantity * units
        return quantity if LoyaltyService._item_qualifies(store, item) else 0

    @staticmethod
    def _combo_loyalty_units(combo):
        """Multiplicador explícito do StoreCombo (metadata['loyalty_units'])."""
        meta = getattr(combo, 'metadata', None) or {}
        try:
            units = int(meta.get('loyalty_units'))
        except (TypeError, ValueError):
            return None
        return units if units > 0 else None

    @staticmethod
    def order_qualified_units(store, order) -> int:
        """Total de selos do pedido: itens comuns + combos reais.

        Combo real (StoreCombo) vira StoreOrderItem com product=None e sem
        categoria → nunca qualificava por categoria. Com
        combo.metadata['loyalty_units'] a linha do combo vale quantity × units
        (substitui a contagem do item pra não duplicar). Sem o metadata,
        mantém o comportamento legado do item.
        """
        combo_units_by_item = {}
        combo_only_total = 0
        try:
            for ci in order.combo_items.select_related('combo').all():
                units = LoyaltyService._combo_loyalty_units(ci.combo) if ci.combo else None
                if units is None:
                    continue
                credited = int(ci.quantity or 0) * units
                if ci.order_item_id:
                    combo_units_by_item[ci.order_item_id] = credited
                else:
                    combo_only_total += credited
        except Exception:
            logger.warning('order_qualified_units: falha ao ler combo_items', exc_info=True)

        total = combo_only_total
        for item in order.items.all():
            explicit = combo_units_by_item.get(item.id)
            if explicit is not None:
                total += explicit
            else:
                total += LoyaltyService.item_qualified_units(store, item)
        return total

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
        qty = LoyaltyService.order_qualified_units(store, order)
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
    def recalculate_order_credit(order):
        """Recalcula o crédito de um pedido já entregue pelas regras de HOJE.

        `credit_order` é uma fotografia: grava a quantidade no momento da
        entrega e nunca mais volta nela (idempotente por unique(order, kind)).
        Quando a loja corrige `loyalty_units` DEPOIS da venda, o pedido antigo
        fica congelado no valor errado — caso Aline Nasche/CE-2608113992, que
        creditou 1 selo por um combo que vale 8.

        Aqui a transação EARN existente é reaberta e o saldo da conta é
        ajustado pela diferença (pra mais ou pra menos). Nunca duplica o
        crédito e nunca deixa o saldo negativo. Devolve
        {before, after, delta, changed, reason}.
        """
        def _resultado(before, after, changed, reason=''):
            return {
                'before': before, 'after': after, 'delta': after - before,
                'changed': changed, 'reason': reason,
            }

        if not order or not getattr(order, 'customer_id', None):
            return _resultado(0, 0, False, 'sem_cliente')

        store = order.store
        _, enabled = LoyaltyService._config(store)
        if not enabled:
            return _resultado(0, 0, False, 'fidelidade_desligada')

        tx = (
            StoreLoyaltyTransaction.objects
            .select_for_update()
            .filter(order=order, kind=StoreLoyaltyTransaction.Kind.EARN)
            .first()
        )
        before = int(tx.quantity) if tx else 0
        after = LoyaltyService.order_qualified_units(store, order)

        if after == before:
            return _resultado(before, after, False, 'sem_mudanca')

        if tx is None:
            LoyaltyService.credit_qualified(store, order.customer, order, after)
            return _resultado(before, after, True, 'creditado')

        account = StoreLoyaltyAccount.objects.select_for_update().get(id=tx.account_id)
        delta = after - before
        # Saldo pode ter sido mexido por fora (resgate, ajuste manual): o piso
        # é zero, senão o recálculo cria dívida que o cliente nunca contraiu.
        novo_saldo = max(0, int(account.qualified_count) + delta)

        if after:
            tx.quantity = after
            tx.note = 'recálculo pelas regras atuais'
            tx.save(update_fields=['quantity', 'note'])
        else:
            # Zerou: apagar a transação libera o pedido pra um crédito futuro.
            tx.delete()

        StoreLoyaltyAccount.objects.filter(id=account.id).update(qualified_count=novo_saldo)
        return _resultado(before, after, True, 'ajustado')

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
