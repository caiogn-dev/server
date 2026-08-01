"""Indicação (gamificação Fase 2).

Fluxo: cliente satisfeito pede um cupom de indicação → recebe INDICA-XXXX
(10%, só primeiro pedido do amigo, multiuso limitado). Quando um amigo usa,
o indicador ganha AMIGO5-XXXX (5%, 1 uso) e é avisado no WhatsApp.

O vínculo indicador↔cupom vive em StoreCoupon.metadata:
  {'type': 'referral', 'referrer_phone': '55...'}
"""
import logging
import uuid as uuid_mod
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

REFERRAL_DISCOUNT_PCT = 10
REFERRAL_USES = 5
REFERRAL_DAYS = 60
REWARD_DISCOUNT_PCT = 5
REWARD_DAYS = 30


class ReferralService:
    @staticmethod
    def get_or_create_referral_coupon(store, referrer_phone: str):
        """Cupom pessoal de indicação — 1 ativo por telefone (idempotente)."""
        from apps.stores.models import StoreCoupon
        now = timezone.now()
        existing = StoreCoupon.objects.filter(
            store=store,
            is_active=True,
            valid_until__gt=now,
            metadata__type='referral',
            metadata__referrer_phone=referrer_phone,
        ).first()
        if existing:
            return existing, False
        coupon = StoreCoupon.objects.create(
            store=store,
            code=f'INDICA-{uuid_mod.uuid4().hex[:4].upper()}',
            discount_type='percentage',
            discount_value=REFERRAL_DISCOUNT_PCT,
            first_order_only=True,
            usage_limit=REFERRAL_USES,
            valid_from=now,
            valid_until=now + timedelta(days=REFERRAL_DAYS),
            metadata={'type': 'referral', 'referrer_phone': referrer_phone},
        )
        return coupon, True

    @staticmethod
    def reward_referrer_if_applicable(order, coupon) -> None:
        """Chamado no resgate: se o cupom é de indicação, premia o indicador.

        Best-effort — nunca pode quebrar o checkout. Auto-indicação (o próprio
        dono do cupom usando) não premia.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCoupon
        try:
            meta = getattr(coupon, 'metadata', None) or {}
            if meta.get('type') != 'referral':
                return
            referrer = normalize_phone_number(meta.get('referrer_phone') or '')
            buyer = normalize_phone_number(order.customer_phone or '')
            if not referrer or referrer == buyer:
                return
            now = timezone.now()
            reward = StoreCoupon.objects.create(
                store=order.store,
                code=f'AMIGO5-{uuid_mod.uuid4().hex[:4].upper()}',
                discount_type='percentage',
                discount_value=REWARD_DISCOUNT_PCT,
                usage_limit=1,
                valid_from=now,
                valid_until=now + timedelta(days=REWARD_DAYS),
                metadata={'type': 'referral_reward', 'source_order': str(order.id)},
            )
            ReferralService._notify_referrer(order.store, meta.get('referrer_phone'), reward)
        except Exception:
            logger.warning('Falha ao premiar indicador do pedido %s', order.id, exc_info=True)

    @staticmethod
    def _notify_referrer(store, phone: str, reward) -> None:
        """Avisa o indicador no WhatsApp (best-effort, janela de 24h)."""
        try:
            account = store.get_whatsapp_account()
            if not account or not getattr(account, 'phone_number_id', None):
                return
            from apps.whatsapp.services import MessageService
            MessageService().send_text_message(
                account_id=str(account.id),
                to=phone,
                text=(
                    'Sua indicação deu certo! 🎉 Um amigo fez o primeiro pedido '
                    f'com o seu cupom.\n\nSeu presente: *{reward.code}* — '
                    f'{REWARD_DISCOUNT_PCT}% de desconto no próximo pedido (até '
                    f'{reward.valid_until.strftime("%d/%m")}).'
                ),
                metadata={'source': 'referral_reward'},
            )
        except Exception:
            logger.warning('Falha ao avisar indicador %s', phone, exc_info=True)
