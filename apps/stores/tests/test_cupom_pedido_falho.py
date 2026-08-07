"""
Pedido com pagamento FALHO não pode queimar o cupom de primeira compra.

Caso real (07/ago, Georgia Silveira / Pastita):
  15:31 — pedido com BEMVINDO10 aplicado (desconto R$9,00, total R$95,00).
          O pagamento falhou → status='failed', payment_status='failed'.
          Mas `increment_usage()` já tinha rodado (used_count 1 → 2).
  15:35 — ela refez o MESMO pedido. `first_order_only` enxergou o pedido
          falho como "primeira compra já feita" e recusou o cupom.
          O pedido saiu com `coupon_code='BEMVINDO10'` e `discount=0,00`:
          a cliente jurava ter aplicado, o painel mostrava o código com
          desconto "-", e ela pagou R$9,00 a mais.

Três invariantes travadas aqui:
  1. Pedido `failed` não conta como compra anterior (nem para
     first_order_only, nem para usage_limit_per_user).
  2. Falhar o pagamento devolve a vaga reservada no cupom.
  3. Cupom recusado no checkout não deixa o código gravado no pedido —
     senão o painel exibe código sem desconto e ninguém entende.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCoupon, StoreOrder

User = get_user_model()

TELEFONE = '63999400616'


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_falho', password='x')
    return Store.objects.create(owner=dono, name='Loja Falho', slug='loja-falho-test')


@pytest.fixture
def cupom(loja):
    return StoreCoupon.objects.create(
        store=loja,
        code='BEMVINDO10',
        discount_type='percentage',
        discount_value=Decimal('10'),
        first_order_only=True,
        is_active=True,
        valid_from=timezone.now() - timezone.timedelta(days=1),
        valid_until=timezone.now() + timezone.timedelta(days=30),
    )


def _pedido(loja, status, payment_status, **extra):
    return StoreOrder.objects.create(
        store=loja,
        customer_name='Georgia',
        customer_phone=TELEFONE,
        status=status,
        payment_status=payment_status,
        subtotal=Decimal('90.00'),
        delivery_fee=Decimal('14.00'),
        total=Decimal('104.00'),
        **extra,
    )


@pytest.mark.django_db
class TestCupomNaoQueimaEmPedidoFalho:

    def test_pedido_falho_nao_bloqueia_primeira_compra(self, loja, cupom):
        """O bug da Georgia: pagamento falhou e o cupom morreu junto."""
        _pedido(loja, StoreOrder.OrderStatus.FAILED, StoreOrder.PaymentStatus.FAILED,
                coupon_code='BEMVINDO10', discount=Decimal('9.00'))

        valido, erro = cupom.is_valid(
            subtotal=Decimal('90.00'), customer_phone=TELEFONE,
        )
        assert valido is True, f'cupom recusado indevidamente: {erro}'

    def test_pedido_cancelado_continua_nao_bloqueando(self, loja, cupom):
        """Regra que já valia — fica travada."""
        _pedido(loja, StoreOrder.OrderStatus.CANCELLED, StoreOrder.PaymentStatus.PENDING)
        assert cupom.is_valid(subtotal=Decimal('90.00'), customer_phone=TELEFONE)[0] is True

    def test_pedido_real_continua_bloqueando(self, loja, cupom):
        """O first_order_only não pode virar letra morta: compra de verdade barra."""
        _pedido(loja, StoreOrder.OrderStatus.PREPARING, StoreOrder.PaymentStatus.PAID)

        valido, erro = cupom.is_valid(subtotal=Decimal('90.00'), customer_phone=TELEFONE)
        assert valido is False
        assert 'primeira compra' in erro

    def test_pedido_falho_nao_conta_no_limite_por_usuario(self, loja, cupom):
        """usage_limit_per_user tem que ignorar tentativa que não virou venda."""
        cupom.first_order_only = False
        cupom.usage_limit_per_user = 1
        cupom.save(update_fields=['first_order_only', 'usage_limit_per_user'])

        _pedido(loja, StoreOrder.OrderStatus.FAILED, StoreOrder.PaymentStatus.FAILED,
                coupon_code='BEMVINDO10', discount=Decimal('9.00'))

        assert cupom.is_valid(subtotal=Decimal('90.00'), customer_phone=TELEFONE)[0] is True


@pytest.mark.django_db
class TestVagaVoltaQuandoPedidoFalha:

    def test_decrement_usage_devolve_a_vaga(self, loja, cupom):
        cupom.usage_limit = 1
        cupom.save(update_fields=['usage_limit'])

        assert cupom.increment_usage() is True
        assert cupom.increment_usage() is False, 'esgotou como esperado'

        cupom.decrement_usage()
        cupom.refresh_from_db()
        assert cupom.used_count == 0
        assert cupom.increment_usage() is True, 'vaga devolvida volta a ser usável'

    def test_decrement_nunca_deixa_contador_negativo(self, loja, cupom):
        cupom.decrement_usage()
        cupom.refresh_from_db()
        assert cupom.used_count == 0
