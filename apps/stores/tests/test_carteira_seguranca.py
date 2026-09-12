"""Saldo de carteira não se gasta só sabendo o telefone de alguém.

O BURACO. O checkout do storefront é guest-first: o telefone chega no corpo da
requisição (`customer_phone`) e nada prova que quem digitou é o dono. Para o
cashback de 3% isso era troco — para uma carteira de R$ 456 é dinheiro de
verdade, e basta conhecer o número de um cliente para gastar o saldo dele.

A REGRA. Crédito PRÉ-PAGO (comprado, o dinheiro grande) só é resgatado com o
telefone COMPROVADO — usuário autenticado cujo cadastro tem aquele número, que
é o que o login por código do WhatsApp já produz. Cashback de compra e de
indicação seguem guest-first: são centavos por pedido, e travá-los esvaziaria
o programa, que foi o erro da fidelidade antiga.

Ou seja: a prova exigida acompanha o valor em risco.
"""
from decimal import Decimal

import pytest

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreOrder, StoreProduct,
)
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.checkout_service import CheckoutService

DONO_DO_SALDO = '5563991386719'
LADRAO = '5563988887777'


@pytest.fixture
def loja(db):
    from django.contrib.auth import get_user_model
    dono = get_user_model().objects.create_user(
        username='dono-seg', email='dono-seg@teste.local', password='x',
    )
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-seg', store_type='food',
        status='active',
        metadata={
            'cashback_enabled': True, 'cashback_percent': '3',
            'cashback_expiry_days': '30',
            'carteira_tiers': [
                {'id': 'familia', 'nome': 'Família', 'paga': '395.00', 'credito': '456.00'},
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


def _pedir(loja, produto, sessao, phone, verificado):
    cart = StoreCart.objects.create(store=loja, session_key=sessao)
    StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)
    return CheckoutService.create_order(
        cart=cart,
        customer_data={'name': 'X', 'email': '', 'phone': phone, 'cpf': ''},
        delivery_data={'method': 'pickup', 'address': {}},
        use_cashback=True,
        telefone_verificado=verificado,
    )


@pytest.mark.django_db
class TestSaldoComprado:

    def _dar_saldo(self, loja):
        return CashbackService.credit_prepaid(
            loja, DONO_DO_SALDO, 'familia', f'carteira-familia-{DONO_DO_SALDO}-s1',
        )

    def test_estranho_com_o_telefone_do_dono_nao_gasta_nada(self, loja, produto):
        """O ataque: digitar o número de um cliente conhecido no checkout."""
        self._dar_saldo(loja)
        pedido = _pedir(loja, produto, 's1', DONO_DO_SALDO, verificado=False)

        assert pedido.discount == Decimal('0.00'), 'saldo de outro foi gasto'
        assert pedido.total == Decimal('38.00')
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=True) == Decimal('456.00')

    def test_o_dono_comprovado_gasta_normalmente(self, loja, produto):
        self._dar_saldo(loja)
        pedido = _pedir(loja, produto, 's1', DONO_DO_SALDO, verificado=True)

        assert pedido.discount == Decimal('38.00')
        assert pedido.total == Decimal('0.00')
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=True) == Decimal('418.00')

    def test_saldo_exibido_sem_prova_e_zero(self, loja):
        """A vitrine não pode anunciar dinheiro que aquele visitante não gasta —
        senão o cliente vê R$ 456 e leva 'cupom inválido' no checkout."""
        self._dar_saldo(loja)
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=False) == Decimal('0.00')
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=True) == Decimal('456.00')


@pytest.mark.django_db
class TestTodoSaldoExigeONumeroComprovado:
    """Até 12/set o cashback de compra saía sem prova ("são centavos"). Com um
    telefone e nada mais dava para ver e GASTAR o saldo de outra pessoa.
    Decisão do dono: todo saldo — cashback, indicação e carteira — só com o
    número confirmado pelo código do WhatsApp."""

    def _dar_cashback(self, loja):
        pedido = StoreOrder.objects.create(
            store=loja, customer_name='C', customer_phone=DONO_DO_SALDO,
            subtotal=Decimal('100.00'), delivery_fee=Decimal('0'),
            discount=Decimal('0'), total=Decimal('100.00'), payment_status='paid',
        )
        return CashbackService.credit_purchase(pedido)

    def test_cashback_de_compra_NAO_sai_sem_comprovar(self, loja, produto):
        lote = self._dar_cashback(loja)
        assert lote.amount == Decimal('3.00')

        pedido = _pedir(loja, produto, 's1', DONO_DO_SALDO, verificado=False)
        assert pedido.discount == Decimal('0.00'), 'saldo gasto por quem só digitou o número'
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=True) == Decimal('3.00')

    def test_comprovado_gasta_cashback_e_carteira(self, loja, produto):
        self._dar_cashback(loja)
        CashbackService.credit_prepaid(
            loja, DONO_DO_SALDO, 'familia', f'carteira-familia-{DONO_DO_SALDO}-s2',
        )
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=False) == Decimal('0.00')
        assert CashbackService.balance(loja, DONO_DO_SALDO, verificado=True) == Decimal('459.00')

        pedido = _pedir(loja, produto, 's1', DONO_DO_SALDO, verificado=True)
        assert pedido.discount > Decimal('0.00')
