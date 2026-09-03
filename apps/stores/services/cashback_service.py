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
    def _lotes_vivos(store, phone: str, verificado: bool = False):
        """Lotes que ESTE visitante pode usar agora.

        A PROVA EXIGIDA ACOMPANHA O VALOR EM RISCO. O checkout é guest-first: o
        telefone chega no corpo da requisição e nada garante que quem digitou é
        o dono. Para o cashback de compra e de indicação isso é aceitável —
        são centavos por pedido, e exigir login esvaziaria o programa, que foi
        exatamente o erro da fidelidade antiga ao chavear por `user`.

        Crédito PRÉ-PAGO é outra coisa: são R$ 456 comprados, e bastaria
        conhecer o número de um cliente para gastar o saldo dele. Esse só sai
        com o telefone comprovado — usuário autenticado cujo cadastro tem
        aquele número, que é o que o login por código do WhatsApp já produz.
        """
        from apps.stores.models import StoreCashbackLot
        variantes = CashbackService._telefones(phone)
        if not variantes:
            return StoreCashbackLot.objects.none()
        qs = StoreCashbackLot.objects.filter(
            store=store, phone__in=variantes,
            remaining__gt=0, expires_at__gt=timezone.now(),
        )
        if not verificado:
            qs = qs.exclude(origin=StoreCashbackLot.Origin.PREPAID)
        return qs

    @staticmethod
    def balance(store, phone: str, verificado: bool = False) -> Decimal:
        """Saldo utilizável por quem está perguntando.

        Sem prova, o pré-pago não entra — a vitrine não pode anunciar dinheiro
        que aquele visitante não conseguiria gastar, senão o cliente vê R$ 456
        e leva um "saldo indisponível" na cara no checkout.
        """
        total = CashbackService._lotes_vivos(store, phone, verificado).aggregate(
            t=Sum('remaining'))['t']
        return _para_centavos(total or Decimal('0'))

    @staticmethod
    def aplicavel(store, phone: str, subtotal, verificado: bool = False) -> Decimal:
        """Quanto do saldo pode virar desconto NESTE pedido.

        O teto é o SUBTOTAL — a comida — e nunca o total com frete. O frete é
        repasse ao entregador: se o saldo o cobrisse, um pacote de 8 saladas
        viraria 6 saladas mais 5 fretes, a loja perderia margem e o cliente
        veria o saldo sumir sem ter comido.

        E nunca mais que a própria comida: saldo maior que a compra viraria
        troco, e crédito de loja não é dinheiro.
        """
        if not CashbackService.is_enabled(store):
            return Decimal('0.00')
        saldo = CashbackService.balance(store, phone, verificado)
        teto = _para_centavos(Decimal(str(subtotal or 0)))
        if teto <= 0:
            return Decimal('0.00')
        return min(saldo, teto)

    @staticmethod
    def expires_next(store, phone: str, verificado: bool = False):
        """Data do saldo que vence primeiro — é o que dá urgência à mensagem."""
        lote = CashbackService._lotes_vivos(store, phone, verificado).order_by('expires_at').first()
        return lote.expires_at if lote else None

    # ── crédito ─────────────────────────────────────────────────────────

    @staticmethod
    def _creditar(store, phone: str, valor: Decimal, origin: str, order=None,
                  coupon_code: str = '', source_ref: str = '', validade_dias: int = None):
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCashbackLot

        valor = _para_centavos(valor)
        if valor <= 0:
            return None
        telefone = normalize_phone_number(phone or '')
        if not telefone:
            return None
        dias = validade_dias if validade_dias is not None else CashbackService.expiry_days(store)
        try:
            # atomic() interno é obrigatório: sem ele o IntegrityError deixa a
            # transação de FORA quebrada, e a próxima query estoura com
            # "current transaction is aborted" em vez de seguir em frente.
            with transaction.atomic():
                return StoreCashbackLot.objects.create(
                    store=store, phone=telefone, origin=origin, amount=valor, remaining=valor,
                    order=order, coupon_code=coupon_code or '', source_ref=source_ref or '',
                    expires_at=timezone.now() + timedelta(days=dias),
                )
        except IntegrityError:
            # Já creditado — por pedido+origem, ou por cobrança (source_ref).
            # A constraint fez o trabalho; repetir aqui em Python seria uma
            # segunda verdade sujeita a corrida.
            return None

    @staticmethod
    def _base_de_bonus(order) -> Decimal:
        """Sobre quanto se paga bônus: dinheiro NOVO que virou COMIDA.

        `order.total` já é líquido do saldo gasto (o checkout soma o cashback
        aplicado em `discount` antes de fechar o total), então tirar o frete
        deixa exatamente `subtotal - descontos`. Duas regras num cálculo só:

        - **O frete sai.** É repasse: a loja cobra R$ 10,72 e paga R$ 10,72 ao
          entregador. Pagar 3% em cima disso é dinheiro saindo do caixa por uma
          venda que não teve margem.
        - **O que foi pago com saldo sai.** Esse real já ganhou 11% de bônus na
          compra do pacote; um segundo bônus é pagar duas vezes pelo mesmo
          dinheiro — e bônus que gera cashback que gera bônus é um laço que só
          anda contra a loja.
        """
        base = Decimal(str(order.total or 0)) - Decimal(str(order.delivery_fee or 0))
        return base if base > 0 else Decimal('0.00')

    @staticmethod
    def credit_purchase(order):
        """Crédito da compra própria. Chamado quando o pedido vira pago."""
        from apps.stores.models import StoreCashbackLot
        store = order.store
        if not CashbackService.is_enabled(store):
            return None
        if getattr(order, 'payment_status', None) != 'paid':
            return None
        base = CashbackService._base_de_bonus(order)
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
        base = CashbackService._base_de_bonus(order)
        valor = base * CashbackService.referral_percent(store) / Decimal('100')
        return CashbackService._creditar(
            store, dono, valor, StoreCashbackLot.Origin.REFERRAL,
            order=order, coupon_code=getattr(coupon, 'code', '') or '',
        )

    # ── resgate ─────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def redeem(store, phone: str, order, amount: Decimal, verificado: bool = False) -> Decimal:
        """Abate `amount` do saldo. Devolve quanto foi realmente abatido.

        Consome os lotes por ordem de VENCIMENTO: o que morre antes sai
        primeiro, senão o cliente perde saldo que poderia ter gasto.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.models import StoreCashbackLot, StoreCashbackRedemption

        pedido = _para_centavos(Decimal(str(amount or 0)))
        if pedido <= 0:
            return Decimal('0.00')

        # Mesmo filtro do cálculo, de propósito: se `aplicavel` recusou o
        # pré-pago por falta de prova, o resgate não pode consumi-lo por trás.
        lotes = list(
            CashbackService._lotes_vivos(store, phone, verificado)
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

    # ── carteira pré-paga ───────────────────────────────────────────────

    @staticmethod
    def tiers(store) -> list:
        """Pacotes que ESTA loja vende. Config, não código.

        Cada loja precifica o próprio bônus — o que sobra numa salada de
        R$ 38 com R$ 20 de custo não é o que sobra numa pizza. Hardcodar a
        escada aqui obrigaria deploy para mudar preço.
        """
        bruto = (getattr(store, 'metadata', None) or {}).get('carteira_tiers') or []
        pacotes = []
        for t in bruto:
            try:
                paga = _para_centavos(Decimal(str(t['paga'])))
                credito = _para_centavos(Decimal(str(t['credito'])))
            except (KeyError, TypeError, ArithmeticError, ValueError):
                logger.warning('carteira: pacote inválido em %s: %r', store.slug, t)
                continue
            # Crédito menor que o preço é pacote que PUNE quem compra adiantado.
            # Melhor sumir da vitrine do que vender isso por engano de cadastro.
            if paga <= 0 or credito < paga:
                logger.warning('carteira: pacote %r de %s não dá bônus', t.get('id'), store.slug)
                continue
            # Cupons de entrega são CONTADOS, nunca ilimitados: o frete é
            # repasse, então cada um sai inteiro da margem, e entrega sempre
            # grátis ainda tira do cliente o motivo de juntar duas saladas na
            # mesma viagem — que é onde a loja ganha mais.
            try:
                cupons = max(0, int(t.get('cupons_entrega') or 0))
            except (TypeError, ValueError):
                cupons = 0
            pacotes.append({
                'id': str(t.get('id') or ''),
                'nome': str(t.get('nome') or ''),
                'paga': paga,
                'credito': credito,
                'bonus': credito - paga,
                'cupons_entrega': cupons,
            })
        return pacotes

    @staticmethod
    def tier(store, tier_id: str):
        return next((t for t in CashbackService.tiers(store) if t['id'] == tier_id), None)

    @staticmethod
    def credit_adjust(store, phone: str, valor, motivo: str, autor=None):
        """Crédito manual do lojista: cortesia, reparação, brinde.

        Existe para tirar isso do shell de produção — creditar cliente pelo
        console é como se perde dinheiro sem rastro. `motivo` é obrigatório
        no chamador; aqui ele é gravado junto do lote.

        Nasce como ADJUST, não como PREPAID, e a diferença é de segurança: o
        pré-pago exige telefone comprovado para ser gasto porque é dinheiro
        comprado; um brinde da loja não faria sentido exigir do cliente que
        provasse o número para receber.
        """
        from apps.stores.models import StoreCashbackLot
        lote = CashbackService._creditar(
            store, phone, valor, StoreCashbackLot.Origin.ADJUST,
            coupon_code=(motivo or '')[:50],
        )
        if lote is not None:
            logger.info(
                'cashback: ajuste manual de %s para %s em %s por %s (%s)',
                lote.amount, lote.phone, store.slug,
                getattr(autor, 'username', '?'), motivo,
            )
        return lote

    @staticmethod
    def credit_prepaid(store, phone: str, tier_id: str, source_ref: str):
        """Credita o pacote comprado. Chamado quando a cobrança vira paga.

        `source_ref` (a cobrança) é obrigatório e é o que torna isto seguro:
        o webhook do Mercado Pago reenvia a mesma notificação, e sem a trava
        de banco o cliente ganharia um pacote a cada reenvio.

        O que entra é o CRÉDITO, não o que foi pago — o bônus é o produto.
        """
        from apps.stores.models import StoreCashbackLot
        if not CashbackService.is_enabled(store):
            return None
        if not (source_ref or '').strip():
            logger.warning('carteira: crédito sem referência de cobrança recusado')
            return None
        pacote = CashbackService.tier(store, tier_id)
        if pacote is None:
            logger.warning('carteira: pacote %r não existe em %s', tier_id, store.slug)
            return None
        return CashbackService._creditar(
            store, phone, pacote['credito'], StoreCashbackLot.Origin.PREPAID,
            source_ref=source_ref.strip(),
        )

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
