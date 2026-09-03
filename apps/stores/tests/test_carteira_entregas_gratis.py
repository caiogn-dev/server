"""Cupons de entrega do pacote Família: contados, nunca ilimitados.

A CONTA QUE DECIDIU ISTO. O frete é repasse — a loja cobra R$ 10,72 e paga
R$ 10,72 ao entregador — então cada entrega grátis sai INTEIRA da margem. No
Família (R$ 395 por 12 saladas, R$ 155 de margem):

    12 viagens de salada única → R$ 128,64 de frete → sobram R$  26
     5 viagens de duas saladas → R$  53,60 de frete → sobram R$ 101

E ilimitado inverte o incentivo: se a entrega é sempre grátis, o cliente perde
o motivo de juntar duas saladas na mesma viagem — que é justamente onde a loja
ganha mais (R$ 25,28 contra R$ 18,00 de uma salada com frete pago).

Por isso são CUPONS: um número fixo, que acaba.
"""
from decimal import Decimal

import pytest

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreDeliveryCoupon,
    StorePayment, StoreProduct,
)
from apps.stores.services.carteira_service import CarteiraService
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.checkout_service import CheckoutService

TELEFONE = '5563991386719'
FRETE = Decimal('10.72')


@pytest.fixture
def loja(db):
    from django.contrib.auth import get_user_model
    dono = get_user_model().objects.create_user(
        username='dono-cupom', email='dono-cupom@teste.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-cupom', store_type='food',
        status='active',
        metadata={
            'cashback_enabled': True,
            'cashback_percent': '3',
            'cashback_expiry_days': '30',
            'carteira_tiers': [
                {'id': 'padrao', 'nome': 'Padrão', 'paga': '270.00', 'credito': '304.00'},
                {'id': 'familia', 'nome': 'Família', 'paga': '395.00',
                 'credito': '456.00', 'cupons_entrega': 5},
            ],
        },
    )


@pytest.fixture
def produto(loja):
    cat = StoreCategory.objects.create(store=loja, name='Saladas', slug='sal')
    return StoreProduct.objects.create(
        store=loja, category=cat, name='Queridinha', slug='q',
        price=Decimal('38.00'), status='active', track_stock=False,
    )


def _pedir(loja, produto, sessao, use_cashback=False):
    cart = StoreCart.objects.create(store=loja, session_key=sessao)
    StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)
    return CheckoutService.create_order(
        cart=cart,
        customer_data={'name': 'Cliente', 'email': '', 'phone': TELEFONE, 'cpf': ''},
        delivery_data={'method': 'delivery', 'address': {}},
        trusted_delivery_fee=FRETE,
        use_cashback=use_cashback,
        telefone_verificado=True,
    )


def _comprar_pacote(loja, tier, ref):
    """O caminho REAL: cobrança paga → webhook → crédito + cupons."""
    cobranca = StorePayment.objects.create(
        store=loja, order=None, amount=Decimal('395.00'),
        payment_method=StorePayment.PaymentMethod.PIX,
        status=StorePayment.PaymentStatus.PENDING,
        external_reference=ref, payer_name='Cliente',
    )
    CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
    return cobranca


@pytest.mark.django_db
class TestConcessao:

    def test_familia_concede_os_cupons_pelo_caminho_real(self, loja):
        """Pelo webhook: `credit_prepaid` sozinho não concede nada, e um teste
        que chamasse só ele passaria sem provar coisa alguma."""
        _comprar_pacote(loja, 'familia', f'carteira-familia-{TELEFONE}-w1')

        cupom = StoreDeliveryCoupon.objects.get(store=loja)
        assert cupom.granted == 5 and cupom.remaining == 5
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('456.00')

    def test_pacote_sem_cupons_nao_concede_nada(self, loja):
        _comprar_pacote(loja, 'padrao', f'carteira-padrao-{TELEFONE}-w2')
        assert not StoreDeliveryCoupon.objects.filter(store=loja).exists()

    def test_cupons_vencem_junto_com_o_saldo(self, loja):
        from apps.stores.models import StoreCashbackLot
        _comprar_pacote(loja, 'familia', f'carteira-familia-{TELEFONE}-w3')
        cupom = StoreDeliveryCoupon.objects.get(store=loja)
        lote = StoreCashbackLot.objects.get(store=loja)
        assert cupom.expires_at == lote.expires_at, (
            'cupom que dura mais que o crédito vira frete grátis eterno'
        )

    def test_webhook_reentregue_nao_dobra_os_cupons(self, loja):
        cobranca = _comprar_pacote(loja, 'familia', f'carteira-familia-{TELEFONE}-w4')
        cobranca.refresh_from_db()
        CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
        assert StoreDeliveryCoupon.objects.filter(store=loja).count() == 1
        assert StoreDeliveryCoupon.objects.get(store=loja).remaining == 5


@pytest.mark.django_db
class TestConsumo:

    def _cupons(self, loja, quantas=5):
        _comprar_pacote(loja, 'familia', f'carteira-familia-{TELEFONE}-c1')
        cupom = StoreDeliveryCoupon.objects.get(store=loja)
        if quantas != 5:
            cupom.remaining = quantas
            cupom.save(update_fields=['remaining'])
        return cupom

    def test_o_pedido_sai_com_frete_zero(self, loja, produto):
        self._cupons(loja)
        pedido = _pedir(loja, produto, 's1')
        assert pedido.delivery_fee == Decimal('0.00')
        assert pedido.total == Decimal('38.00'), 'o cliente pagou só a comida'

    def test_cada_pedido_gasta_UM_cupom(self, loja, produto):
        cupom = self._cupons(loja)
        _pedir(loja, produto, 's1')
        _pedir(loja, produto, 's2')
        cupom.refresh_from_db()
        assert cupom.remaining == 3

    def test_acabaram_os_cupons_o_frete_volta_a_ser_cobrado(self, loja, produto):
        """O teto é o ponto da feature: sem ele a margem do Família some."""
        self._cupons(loja, quantas=1)
        primeiro = _pedir(loja, produto, 's1')
        segundo = _pedir(loja, produto, 's2')
        assert primeiro.delivery_fee == Decimal('0.00')
        assert segundo.delivery_fee == FRETE, 'cupom virou frete grátis ilimitado'

    def test_sem_pacote_o_frete_e_cobrado_normal(self, loja, produto):
        pedido = _pedir(loja, produto, 's1')
        assert pedido.delivery_fee == FRETE

    def test_o_saldo_continua_sem_pagar_frete(self, loja, produto):
        """Guarda: o cupom zera o frete; o SALDO nunca o paga."""
        self._cupons(loja)
        pedido = _pedir(loja, produto, 's1', use_cashback=True)
        assert pedido.delivery_fee == Decimal('0.00')
        assert pedido.discount == Decimal('38.00')  # abateu só a comida
        assert pedido.total == Decimal('0.00')
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('418.00')
