"""Carteira pré-paga: o cliente compra saldo adiantado e ganha bônus.

POR QUE ISTO EXISTE, EM NÚMEROS DA CÊ SALADAS (12 semanas, 129 pedidos):
81 clientes únicos, e 57 deles compraram UMA vez e nunca voltaram. Os 13 que
voltaram três ou mais vezes são 45% do faturamento. O problema da loja não é
ticket, é segunda compra — e saldo comprado adiantado é a única mecânica que
resolve isso sem descontar a comida, porque enquanto houver saldo o cliente
não pede em outro lugar.

TRÊS DECISÕES QUE MOLDAM ESTE ARQUIVO:

1. **A chave é o TELEFONE.** O saldo mora em `StoreCashbackLot`, que já é por
   telefone justamente porque o checkout do storefront é guest-first. Exigir
   login para usar a carteira mataria o produto no cadastro.

2. **A cobrança vira VENDA.** Sem o pedido, os R$ 270 somem do relatório: os
   pedidos seguintes saem com desconto e faturamento nenhum, e o mês fecha
   como se a loja não tivesse vendido. O pedido nasce `digital` e com
   `source='carteira'` porque o BI agrupa por `source` — foi mislabelar isso
   que fez a tela de canais mentir em 15/ago.

3. **O crédito é IDEMPOTENTE por cobrança**, garantido por constraint
   (`cashback_unico_por_cobranca`). O Mercado Pago reentrega webhook; sem a
   trava de banco, cada reentrega dá um pacote de graça.
"""
import logging
import uuid
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIXO = 'carteira'
SEP = '-'


def _ref(tier_id: str, telefone: str) -> str:
    """`carteira-<pacote>-<telefone>-<nonce>`.

    HÍFEN, NÃO DOIS-PONTOS. A Orders API do Mercado Pago (a rota que gera o
    QR do PIX desde 19/08) valida `external_reference` contra um padrão que
    recusa `:` — devolve 400 `'$.external_reference' - does not match pattern`
    e a cobrança cai no fallback de link de pagamento, sem QR nenhum. Os
    vocabulários antigos (`splink:`, `subpix:`) nunca bateram nisso porque só
    passam pelo Checkout Pro, que é mais permissivo.

    O nonce é obrigatório pelo motivo OPOSTO à idempotência: sem ele, o mesmo
    cliente comprando o mesmo pacote duas vezes no mês geraria a mesma
    referência, e a constraint recusaria a SEGUNDA COMPRA LEGÍTIMA — o cliente
    pagaria e não receberia saldo.
    """
    return SEP.join([PREFIXO, str(tier_id), str(telefone), uuid.uuid4().hex[:12]])


def decompor(external_reference: str):
    """Devolve (tier_id, telefone) de uma referência de carteira, ou None.

    Lê das PONTAS, não da esquerda: o id do pacote é livre no painel e um
    `id: 'meu-pacote'` partiria o parse posicional. Prefixo e nonce são fixos
    nas extremidades, o telefone é o penúltimo, e o que sobra no meio é o
    pacote — inclusive com hífen dentro.
    """
    partes = str(external_reference or '').split(SEP)
    if len(partes) < 4 or partes[0] != PREFIXO:
        return None
    tier_id = SEP.join(partes[1:-2])
    telefone = partes[-2]
    if not tier_id or not telefone:
        return None
    return tier_id, telefone


def telefone_comprovado(request, telefone_informado: str) -> bool:
    """O visitante provou ser o dono deste número?

    A prova é o login por código do WhatsApp — e SÓ ele. Até 14/set valia
    "logado + `profile.phone` batendo", mas o perfil é gravável pelo próprio
    cliente (PATCH /auth/profile/, cadastro, checkout logado): bastava pôr o
    número da vítima no perfil para ler o saldo, o histórico com
    `access_token` (→ endereço de casa) e gastar a carteira dela.

    Duas provas aceitas:
    - `profile.telefone_verificado`, gravado por verify_whatsapp_auth_code;
    - legado: username `cliente_<dígitos>` SEM senha utilizável — conta que o
      próprio OTP criou e que não tem outra porta para receber token. A senha
      importa: o cadastro por e-mail deriva o username da parte local do
      e-mail, e `cliente_5563...@x.com` produziria o mesmo username com senha.

    Compara por VARIANTES e não por igualdade: o wa_id do WhatsApp vem sem o
    nono dígito e o site grava com ele.
    """
    import re

    from apps.core.utils import phone_variants

    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return False

    provas = []
    perfil = getattr(user, 'profile', None)
    verificado = (getattr(perfil, 'telefone_verificado', '') or '').strip()
    if verificado:
        provas.append(verificado)
    if not user.has_usable_password():
        achou = re.fullmatch(r'cliente_(\d{10,13})', getattr(user, 'username', '') or '')
        if achou:
            provas.append(achou.group(1))
    if not provas or not telefone_informado:
        return False

    informadas = set(phone_variants(telefone_informado))
    return any(informadas & set(phone_variants(p)) for p in provas)


def e_de_carteira(external_reference: str) -> bool:
    return str(external_reference or '').startswith(f'{PREFIXO}{SEP}')


class CarteiraService:

    @staticmethod
    def pacotes(store) -> list:
        from apps.stores.services.cashback_service import CashbackService
        return CashbackService.tiers(store)

    @staticmethod
    def saldo(store, phone: str, verificado: bool = False) -> dict:
        """O que a vitrine mostra: quanto tem e quando some.

        `expira_em` não é enfeite — saldo sem data visível é saldo que o
        cliente descobre ter perdido, e isso não gera recompra, gera briga.
        """
        from apps.stores.services.cashback_service import CashbackService
        vence = CashbackService.expires_next(store, phone, verificado)
        return {
            'saldo': str(CashbackService.balance(store, phone, verificado)),
            'expira_em': vence.isoformat() if vence else None,
            'cupons_entrega': CarteiraService.cupons_de_entrega_disponiveis(store, phone),
        }

    @staticmethod
    def comprar(store, phone: str, tier_id: str, payer_name: str = '',
                payer_email: str = '', payment_payload: dict = None) -> dict:
        """Gera a cobrança PIX de um pacote. O saldo só entra quando ela é paga.

        Creditar aqui, na intenção de compra, seria dar saldo a quem abriu a
        tela e nunca pagou.
        """
        from apps.core.utils import normalize_phone_number
        from apps.stores.services.cashback_service import CashbackService
        from apps.stores.services.checkout_service import CheckoutService

        telefone = normalize_phone_number(phone or '')
        if not telefone:
            raise ValueError('Informe um celular válido para receber o saldo.')

        pacote = CashbackService.tier(store, tier_id)
        if pacote is None:
            raise ValueError('Pacote indisponível.')
        if not CashbackService.is_enabled(store):
            raise ValueError('A carteira não está ativa nesta loja.')

        payload = dict(payment_payload or {})
        payload['external_reference'] = _ref(pacote['id'], telefone)
        payload['payer_name'] = payer_name or 'Cliente'
        if payer_email:
            payload['payer_email'] = payer_email

        resultado = CheckoutService.create_payment(
            order=None,
            payment_method='pix',
            payment_data=payload,
            amount=pacote['paga'],
            store=store,
            description=f'Carteira {store.name} · Pacote {pacote["nome"]}',
        )
        resultado['pacote'] = {
            'id': pacote['id'], 'nome': pacote['nome'],
            'paga': str(pacote['paga']), 'credito': str(pacote['credito']),
            'bonus': str(pacote['bonus']),
        }
        return resultado

    # ── entregas grátis do pacote ───────────────────────────────────────

    @staticmethod
    def cupons_de_entrega_disponiveis(store, phone: str) -> int:
        from apps.stores.models import StoreDeliveryCoupon
        from apps.stores.services.cashback_service import CashbackService
        from django.db.models import Sum
        from django.utils import timezone as tz

        variantes = CashbackService._telefones(phone)
        if not variantes:
            return 0
        total = StoreDeliveryCoupon.objects.filter(
            store=store, phone__in=variantes,
            remaining__gt=0, expires_at__gt=tz.now(),
        ).aggregate(t=Sum('remaining'))['t']
        return int(total or 0)

    @staticmethod
    def consumir_cupom_de_entrega(store, phone: str, order, valor):
        """Zera o frete deste pedido usando uma entrega do pacote.

        Devolve o valor abatido. Consome o benefício que vence ANTES, pelo
        mesmo motivo do saldo: o cliente não pode perder o que daria para usar.

        Idempotente por pedido via constraint: um retry do checkout ou um
        recálculo de totais gastaria duas entregas pelo mesmo pedido.
        """
        from decimal import Decimal
        from django.db import IntegrityError, transaction
        from django.utils import timezone as tz
        from apps.stores.models import StoreDeliveryCoupon, StoreDeliveryCouponUse
        from apps.stores.services.cashback_service import CashbackService

        valor = Decimal(str(valor or 0))
        if valor <= 0 or order is None:
            return Decimal('0.00')
        variantes = CashbackService._telefones(phone)
        if not variantes:
            return Decimal('0.00')

        cupom = (
            StoreDeliveryCoupon.objects
            .select_for_update()
            .filter(store=store, phone__in=variantes,
                    remaining__gt=0, expires_at__gt=tz.now())
            .order_by('expires_at', 'created_at')
            .first()
        )
        if cupom is None:
            return Decimal('0.00')
        try:
            with transaction.atomic():
                StoreDeliveryCouponUse.objects.create(cupom=cupom, order=order, amount=valor)
        except IntegrityError:
            # Pedido já usou uma entrega — não gasta outra.
            return Decimal('0.00')
        cupom.remaining -= 1
        cupom.save(update_fields=['remaining'])
        return valor

    @staticmethod
    def aplicar_pagamento(store_payment):
        """Cobrança de pacote foi paga: credita o saldo e registra a venda.

        Nesta ordem de propósito. Se a criação do pedido falhar, o cliente já
        tem o saldo que pagou — um relatório furado se conserta depois, um
        cliente sem o saldo que comprou vira reembolso e desconfiança.
        """
        from apps.stores.services.cashback_service import CashbackService

        partes = decompor(store_payment.external_reference)
        if partes is None:
            logger.warning(
                'carteira: cobrança %s sem referência decifrável (%r)',
                store_payment.id, store_payment.external_reference,
            )
            return None
        tier_id, telefone = partes
        store = store_payment.store

        lote = CashbackService.credit_prepaid(
            store, telefone, tier_id=tier_id,
            source_ref=str(store_payment.external_reference),
        )
        if lote is None:
            # Já creditado (webhook reentregue) ou pacote saiu do catálogo.
            # Nos dois casos não se credita de novo nem se duplica a venda.
            logger.info('carteira: cobrança %s não gerou crédito novo', store_payment.id)
            return store_payment.order

        CarteiraService._conceder_cupons_de_entrega(store, telefone, tier_id, lote)
        return CarteiraService._venda_do_pacote(store_payment, tier_id, lote)

    @staticmethod
    def _conceder_cupons_de_entrega(store, telefone, tier_id, lote):
        """Entregas grátis do pacote, quando o pacote as vende.

        Mesma validade do saldo de propósito: benefício que dura mais que o
        crédito viraria frete grátis para sempre em quem comprou uma vez.
        """
        from apps.stores.models import StoreDeliveryCoupon
        from apps.stores.services.cashback_service import CashbackService
        from django.db import IntegrityError, transaction

        pacote = CashbackService.tier(store, tier_id) or {}
        quantas = int(pacote.get('cupons_entrega') or 0)
        if quantas <= 0:
            return None
        try:
            with transaction.atomic():
                return StoreDeliveryCoupon.objects.create(
                    store=store, phone=lote.phone,
                    remaining=quantas, granted=quantas,
                    expires_at=lote.expires_at,
                    source_ref=lote.source_ref or '',
                )
        except IntegrityError:
            return None

    @staticmethod
    def _cadastrar_cliente(store, telefone: str, nome: str = ''):
        """Garante usuário + StoreCustomer para quem comprou saldo. Nunca levanta:
        crédito concedido não pode ser desfeito por falha de cadastro."""
        from apps.core.services.customer_identity import CustomerIdentityService
        from apps.stores.models import StoreCustomer

        try:
            usuario, _perfil, _criado = CustomerIdentityService.resolve_user(
                phone=telefone, full_name=(nome or '').strip(), create=True,
            )
            if usuario is None:
                return None
            StoreCustomer.objects.get_or_create(
                store=store, user=usuario, defaults={'phone': telefone, 'whatsapp': telefone},
            )
            return usuario
        except Exception as exc:  # noqa: BLE001 — cadastro é acessório do crédito
            logger.warning('carteira: não cadastrou o cliente %s: %s', telefone, exc)
            return None

    @staticmethod
    def _venda_do_pacote(store_payment, tier_id: str, lote):
        """A venda do pacote no relatório.

        O valor da venda é o que ENTROU (`store_payment.amount`, R$ 270), nunca
        o crédito concedido (R$ 304): faturamento é dinheiro recebido. O bônus
        aparece sozinho depois, como desconto nos pedidos que gastarem o saldo.
        """
        from apps.stores.models import StoreOrder, StoreOrderItem
        from apps.stores.services.cashback_service import CashbackService

        store_payment.refresh_from_db()
        if store_payment.order_id:
            return store_payment.order

        pacote = CashbackService.tier(store_payment.store, tier_id) or {}
        nome = pacote.get('nome') or tier_id

        order = StoreOrder.objects.create(
            store=store_payment.store,
            total=store_payment.amount,
            subtotal=store_payment.amount,
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PAID,
            payment_method=store_payment.payment_method or 'pix',
            paid_at=store_payment.paid_at or timezone.now(),
            customer_name=store_payment.payer_name or 'Cliente',
            customer_phone=lote.phone,
            # 'digital': não tem comida para preparar nem endereço para ir.
            # A comanda precisa dizer isso, senão a cozinha monta uma salada
            # que ninguém pediu.
            delivery_method=StoreOrder.DeliveryMethod.DIGITAL,
            # O BI agrupa por `source`. Deixar cair em 'web' creditaria o
            # cardápio por uma venda que não passou por ele.
            source='carteira',
            metadata={
                'origem': 'carteira_prepaga',
                'pacote': tier_id,
                'credito_concedido': str(lote.amount),
                'store_payment_id': str(store_payment.id),
            },
        )
        StoreOrderItem.objects.create(
            order=order,
            # `product` nulo de propósito: inventar um item de cardápio sujaria
            # estoque e ranking de mais vendidos com algo que não é comida.
            product=None,
            product_name=f'Carteira · Pacote {nome} (saldo de R$ {lote.amount})',
            unit_price=store_payment.amount,
            quantity=1,
            subtotal=store_payment.amount,
        )
        store_payment.order = order
        store_payment.save(update_fields=['order', 'updated_at'])
        # Quem comprou saldo é CLIENTE da loja — precisa existir em Clientes.
        # 26/09: Flaviane comprou o Pacote Leve e não aparecia em lugar nenhum
        # do painel (nem Clientes, nem a ficha), porque só o lote e o pedido
        # nasciam; ninguém criava a pessoa.
        usuario = CarteiraService._cadastrar_cliente(store_payment.store, lote.phone, store_payment.payer_name)
        if usuario is not None:
            order.customer = usuario
            order.save(update_fields=['customer'])
        logger.info(
            'carteira: pacote %s creditado para %s (R$ %s) — pedido %s',
            tier_id, lote.phone, lote.amount, order.order_number,
        )
        return order
