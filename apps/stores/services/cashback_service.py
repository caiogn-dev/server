"""Cashback por telefone: crédito de compra, crédito de indicação e resgate.

TRÊS DECISÕES QUE MOLDAM ESTE ARQUIVO:

1. A chave é o TELEFONE, nunca o usuário. O checkout do storefront é
   guest-first e a maioria dos pedidos não tem login. A fidelidade antiga
   (LoyaltyService.credit_qualified) exige `user` e por isso não credita
   pedido de convidado — o programa fica vazio sem ninguém perceber.

2. O saldo vive em LOTES com validade própria (StoreCashbackLot), não num
   campo único. Cada crédito vence 60 dias depois de nascer; com um saldo só
   não há como saber que parte venceu.

3. Crédito e resgate são IDEMPOTENTES por pedido, garantido por constraint no
   banco e não por `if` no Python. O webhook do Mercado Pago reenvia a mesma
   notificação e um crédito duplicado é dinheiro que a loja paga duas vezes.
"""
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

PERCENTUAL_PADRAO = Decimal('3')
PERCENTUAL_INDICACAO_PADRAO = Decimal('5')
DIAS_PARA_VENCER = 60
CENTAVO = Decimal('0.01')


def _para_centavos(valor: Decimal) -> Decimal:
    """Arredonda PARA BAIXO. Meio centavo a mais, multiplicado por pedido,
    é a loja pagando cashback que ela não prometeu."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_DOWN)


class CashbackService:

    # ── configuração da loja ────────────────────────────────────────────

    @staticmethod
    def is_enabled(store) -> bool:
        return bool((getattr(store, 'metadata', None) or {}).get('cashback_enabled'))

    @staticmethod
    def _config(store, chave: str, padrao: Decimal) -> Decimal:
        bruto = (getattr(store, 'metadata', None) or {}).get(chave)
        if bruto in (None, ''):
            return padrao
        try:
            return Decimal(str(bruto))
        except Exception:
            logger.warning('cashback: %s inválido em %s: %r', chave, store.slug, bruto)
            return padrao

    @staticmethod
    def percent(store) -> Decimal:
        return CashbackService._config(store, 'cashback_percent', PERCENTUAL_PADRAO)

    @staticmethod
    def referral_percent(store) -> Decimal:
        return CashbackService._config(store, 'cashback_referral_percent', PERCENTUAL_INDICACAO_PADRAO)

    @staticmethod
    def expiry_days(store) -> int:
        return int(CashbackService._config(store, 'cashback_expiry_days', Decimal(DIAS_PARA_VENCER)))

    # ── identidade ──────────────────────────────────────────────────────

    @staticmethod
    def _telefones(phone: str) -> list:
        """Todas as formas do MESMO telefone. O wa_id do WhatsApp vem sem o
        nono dígito e o site grava com ele — buscar por igualdade exata perde
        metade dos créditos do próprio cliente."""
        from apps.core.utils import phone_variants
        return [p for p in phone_variants(phone or '') if p]

    # ── saldo ───────────────────────────────────────────────────────────

    @staticmethod
    def _lotes_vivos(store, phone: str):
        from apps.stores.models import StoreCashbackLot
        variantes = CashbackService._telefones(phone)
        if not variantes:
            return StoreCashbackLot.objects.none()
        return StoreCashbackLot.objects.filter(
            store=store, phone__in=variantes,
            remaining__gt=0, expires_at__gt=timezone.now(),
        )

    @staticmethod
    def balance(store, phone: str) -> Decimal:
        total = CashbackService._lotes_vivos(store, phone).aggregate(t=Sum('remaining'))['t']
        return _para_centavos(total or Decimal('0'))

    @staticmethod
    def aplicavel(store, phone: str, total) -> Decimal:
        """Quanto do saldo pode virar desconto NESTE pedido.

        Nunca mais que o próprio total: saldo maior que a compra viraria total
        negativo ou troco, e cashback é crédito de loja, não dinheiro.
        """
        if not CashbackService.is_enabled(store):
            return Decimal('0.00')
        saldo = CashbackService.balance(store, phone)
        teto = _para_centavos(Decimal(str(total or 0)))
        if teto <= 0:
            return Decimal('0.00')
        return min(saldo, teto)

    @staticmethod
    def expires_next(store, phone: str):
        """Data do saldo que vence primeiro — é o que dá urgência à mensagem."""
        lote = CashbackService._lotes_vivos(store, phone).order_by('expires_at').first()
        return lote.expires_at if lote else None

    # ── crédito ─────────────────────────────────────────────────────────

    @staticmethod
    def _creditar(store, phone: str, valor: Decimal, origin: str, order=None, coupon_code: str = ''):
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCashbackLot

        valor = _para_centavos(valor)
        if valor <= 0:
            return None
        telefone = normalize_phone_number(phone or '')
        if not telefone:
            return None
        try:
            # atomic() interno é obrigatório: sem ele o IntegrityError deixa a
            # transação de FORA quebrada, e a próxima query estoura com
            # "current transaction is aborted" em vez de seguir em frente.
            with transaction.atomic():
                return StoreCashbackLot.objects.create(
                    store=store, phone=telefone, origin=origin, amount=valor, remaining=valor,
                    order=order, coupon_code=coupon_code or '',
                    expires_at=timezone.now() + timedelta(days=CashbackService.expiry_days(store)),
                )
        except IntegrityError:
            # Pedido já creditado nesta origem — constraint fez o trabalho.
            return None

    @staticmethod
    def credit_purchase(order):
        """Crédito da compra própria. Chamado quando o pedido vira pago."""
        from apps.stores.models import StoreCashbackLot
        store = order.store
        if not CashbackService.is_enabled(store):
            return None
        if getattr(order, 'payment_status', None) != 'paid':
            return None
        base = Decimal(str(order.total or 0))
        valor = base * CashbackService.percent(store) / Decimal('100')
        return CashbackService._creditar(
            store, order.customer_phone, valor, StoreCashbackLot.Origin.PURCHASE, order=order,
        )

    @staticmethod
    def credit_referral(order, coupon, owner_phone: str = ''):
        """Crédito de indicação: o DONO do cupom ganha % do que o amigo gastou.

        Substitui o cupom-por-indicação (INDICA-XXXX/AMIGO5-XXXX), que gerava
        um código novo a cada indicação — 13 criados, zero usados, e a lista de
        cupons do painel virou um depósito de códigos que ninguém digita.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCashbackLot
        store = order.store
        if not CashbackService.is_enabled(store):
            return None
        dono = (owner_phone or '').strip() or (
            (getattr(coupon, 'metadata', None) or {}).get('owner_phone') or ''
        ).strip()
        if not dono:
            return None
        # Auto-indicação é desconto, não indicação.
        if normalize_phone_number(dono) == normalize_phone_number(order.customer_phone or ''):
            return None
        base = Decimal(str(order.total or 0))
        valor = base * CashbackService.referral_percent(store) / Decimal('100')
        return CashbackService._creditar(
            store, dono, valor, StoreCashbackLot.Origin.REFERRAL,
            order=order, coupon_code=getattr(coupon, 'code', '') or '',
        )

    # ── resgate ─────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def redeem(store, phone: str, order, amount: Decimal) -> Decimal:
        """Abate `amount` do saldo. Devolve quanto foi realmente abatido.

        Consome os lotes por ordem de VENCIMENTO: o que morre antes sai
        primeiro, senão o cliente perde saldo que poderia ter gasto.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCashbackLot, StoreCashbackRedemption

        pedido = _para_centavos(Decimal(str(amount or 0)))
        if pedido <= 0:
            return Decimal('0.00')

        lotes = list(
            CashbackService._lotes_vivos(store, phone)
            .order_by('expires_at', 'created_at')
            .select_for_update()
        )
        abatido = Decimal('0.00')
        for lote in lotes:
            if abatido >= pedido:
                break
            usa = min(lote.remaining, pedido - abatido)
            lote.remaining = lote.remaining - usa
            abatido += usa
        if abatido <= 0:
            return Decimal('0.00')

        try:
            with transaction.atomic():
                StoreCashbackRedemption.objects.create(
                    store=store, phone=normalize_phone_number(phone or ''),
                    amount=abatido, order=order,
                )
        except IntegrityError:
            # Pedido já resgatou — não abate de novo nem toca nos lotes.
            return Decimal('0.00')

        StoreCashbackLot.objects.bulk_update(lotes, ['remaining'])
        return abatido

    # ── gancho único ────────────────────────────────────────────────────

    @staticmethod
    def credit_order(order) -> None:
        """Credita compra + indicação de um pedido que acabou de virar pago.

        É o único ponto de entrada usado em produção. Best-effort de
        propósito: roda dentro da transição de status do pedido, e uma exceção
        aqui deixaria um pedido pago sem confirmar — o cashback é importante,
        mas não mais do que o pedido.
        """
        from apps.stores.models import StoreCoupon
        try:
            if order is None:
                return
            CashbackService.credit_purchase(order)

            # Quem indicou vem do LINK primeiro. O cupom voltou a ser fixo
            # (INDICA10) para ser ditável no WhatsApp, e código igual para
            # todos não carrega identidade — o link carrega.
            #
            # A ordem importa: link ganha do cupom de parceiro, e sai UM
            # crédito só. Dois créditos de indicação no mesmo pedido é a loja
            # pagando duas vezes pela mesma venda.
            indicador = ((getattr(order, 'metadata', None) or {}).get('indicado_por') or '').strip()
            if indicador:
                CashbackService.credit_referral(order, None, owner_phone=indicador)
                return

            codigo = (getattr(order, 'coupon_code', '') or '').strip()
            if not codigo:
                return
            cupom = StoreCoupon.objects.filter(store=order.store, code=codigo).first()
            if cupom is not None:
                CashbackService.credit_referral(order, cupom)
        except Exception:
            logger.warning(
                'Falha ao creditar cashback do pedido %s', getattr(order, 'id', '?'),
                exc_info=True,
            )
