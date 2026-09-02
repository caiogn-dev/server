"""Cashback fechando o ciclo: o saldo vira desconto e a indicação é atribuída.

Até aqui o crédito entrava e nunca saía — CashbackService.redeem existia,
testado, e não era chamado por ninguém. Saldo que não vira desconto é
promessa que a loja não cumpre.

O RESGATE É OPT-IN: o cliente decide no carrinho se gasta agora ou guarda.
Aplicar sozinho seria mais simples, mas o saldo é dele e some em 60 dias —
quem escolhe quando queimar é quem vai sentir falta.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService

TELEFONE = '5563999547790'
INDICADOR = '5563988887777'


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(
        username='dono-cbck', email='dono-cbck@teste.local', password='x',
    )


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Loja CBCK', slug='loja-cbck', store_type='food',
        status='active', metadata={'cashback_enabled': True},
    )


def _saldo(loja, valor, phone=TELEFONE, dias=60):
    return StoreCashbackLot.objects.create(
        store=loja, phone=phone, amount=Decimal(valor), remaining=Decimal(valor),
        expires_at=timezone.now() + timedelta(days=dias),
    )


def _pedido(loja, total, phone=TELEFONE, **kw):
    return StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_phone=phone,
        subtotal=Decimal(str(total)), total=Decimal(str(total)),
        payment_status='paid', **kw,
    )


@pytest.mark.django_db
class TestQuantoPodeAbater:
    """`aplicavel` é o que o checkout pergunta antes de montar o total."""

    def test_abate_o_saldo_inteiro_quando_cabe_no_pedido(self, loja):
        _saldo(loja, '10.00')
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('72.00')) == Decimal('10.00')

    def test_nunca_abate_mais_que_o_pedido(self, loja):
        """Saldo maior que a compra não pode gerar total negativo nem troco."""
        _saldo(loja, '100.00')
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('30.00')) == Decimal('30.00')

    def test_sem_saldo_e_zero(self, loja):
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('72.00')) == Decimal('0.00')

    def test_saldo_vencido_nao_conta(self, loja):
        _saldo(loja, '10.00', dias=-1)
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('72.00')) == Decimal('0.00')

    def test_loja_com_cashback_desligado_nao_oferece(self, db, dono):
        loja = Store.objects.create(
            owner=dono, name='Off', slug='off-cbck', store_type='food', status='active',
        )
        _saldo(loja, '10.00')
        assert CashbackService.aplicavel(loja, TELEFONE, Decimal('72.00')) == Decimal('0.00')


@pytest.mark.django_db
class TestAtribuicaoDaIndicacao:
    """Quem indicou vem do LINK, não do código do cupom.

    O cupom voltou a ser fixo (INDICA10) para ser ditável, e código igual para
    todos não carrega identidade. O link (?indica=<telefone>) carrega.
    """

    def test_credita_quem_indicou_pelo_telefone_no_pedido(self, loja):
        pedido = _pedido(loja, '100.00', metadata={'indicado_por': INDICADOR})
        CashbackService.credit_order(pedido)
        assert CashbackService.balance(loja, INDICADOR) == Decimal('5.00')

    def test_quem_comprou_ganha_o_dele_tambem(self, loja):
        pedido = _pedido(loja, '100.00', metadata={'indicado_por': INDICADOR})
        CashbackService.credit_order(pedido)
        assert CashbackService.balance(loja, TELEFONE) == Decimal('3.00')

    def test_auto_indicacao_nao_premia(self, loja):
        pedido = _pedido(loja, '100.00', metadata={'indicado_por': TELEFONE})
        CashbackService.credit_order(pedido)
        assert CashbackService.balance(loja, TELEFONE) == Decimal('3.00')
        assert StoreCashbackLot.objects.filter(origin='referral').count() == 0

    def test_indicador_com_nono_digito_diferente_e_a_mesma_pessoa(self, loja):
        """wa_id do WhatsApp vem sem o nono dígito; o link pode levar com."""
        _saldo(loja, '0.01', phone=INDICADOR)
        pedido = _pedido(loja, '100.00', metadata={'indicado_por': '556388887777'})
        CashbackService.credit_order(pedido)
        assert CashbackService.balance(loja, INDICADOR) == Decimal('5.01')

    def test_link_e_cupom_de_parceiro_nao_pagam_duas_vezes(self, loja):
        """Se o pedido tem link E cupom com dono, sai UM crédito de indicação."""
        from apps.stores.models import StoreCoupon
        agora = timezone.now()
        StoreCoupon.objects.create(
            store=loja, code='NUTRI.MARI', discount_type='percentage', discount_value=5,
            valid_from=agora, valid_until=agora + timedelta(days=365),
            metadata={'owner_phone': '5563977776666'},
        )
        pedido = _pedido(
            loja, '100.00', coupon_code='NUTRI.MARI',
            metadata={'indicado_por': INDICADOR},
        )
        CashbackService.credit_order(pedido)
        assert StoreCashbackLot.objects.filter(origin='referral').count() == 1

    def test_pedido_sem_indicacao_nao_quebra(self, loja):
        CashbackService.credit_order(_pedido(loja, '100.00'))
        assert StoreCashbackLot.objects.filter(origin='referral').count() == 0


@pytest.mark.django_db
class TestResgateNoCheckout:
    """O ciclo fechado: saldo vira desconto no pedido, uma vez só."""

    def _carrinho(self, loja, preco='72.00'):
        from apps.stores.models import StoreCart, StoreCartItem, StoreProduct, StoreCategory
        cat = StoreCategory.objects.create(store=loja, name='Saladas', slug='saladas')
        prod = StoreProduct.objects.create(
            store=loja, category=cat, name='Salada', slug='salada',
            price=Decimal(preco), is_active=True, track_stock=False,
        )
        cart = StoreCart.objects.create(store=loja, session_key='sess-cbck')
        StoreCartItem.objects.create(cart=cart, product=prod, quantity=1)
        return cart

    def _dados(self):
        return {'name': 'Cliente', 'phone': TELEFONE, 'email': 'c@x.com'}

    def test_saldo_vira_desconto_no_total(self, loja):
        from apps.stores.services.checkout_service import CheckoutService
        _saldo(loja, '10.00')
        pedido = CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'}, use_cashback=True,
        )
        assert pedido.total == Decimal('62.00')
        assert pedido.metadata['cashback_aplicado'] == 10.0

    def test_sem_pedir_nao_gasta_o_saldo(self, loja):
        """Opt-in: quem não marcou continua com o saldo intacto."""
        from apps.stores.services.checkout_service import CheckoutService
        _saldo(loja, '10.00')
        pedido = CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'},
        )
        assert pedido.total == Decimal('72.00')
        assert CashbackService.balance(loja, TELEFONE) == Decimal('10.00')

    def test_saldo_e_debitado_de_verdade(self, loja):
        from apps.stores.services.checkout_service import CheckoutService
        _saldo(loja, '10.00')
        CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'}, use_cashback=True,
        )
        assert CashbackService.balance(loja, TELEFONE) == Decimal('0.00')

    def test_saldo_maior_que_o_pedido_nao_gera_total_negativo(self, loja):
        from apps.stores.services.checkout_service import CheckoutService
        _saldo(loja, '500.00')
        pedido = CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'}, use_cashback=True,
        )
        assert pedido.total == Decimal('0.00')
        assert CashbackService.balance(loja, TELEFONE) == Decimal('428.00')

    def test_sem_saldo_o_pedido_sai_normal(self, loja):
        from apps.stores.services.checkout_service import CheckoutService
        pedido = CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'}, use_cashback=True,
        )
        assert pedido.total == Decimal('72.00')

    def test_o_link_de_indicacao_fica_gravado_no_pedido(self, loja):
        """O crédito só sai quando o pedido é PAGO — nessa hora o carrinho e a
        sessão do navegador já não existem, então quem indicou vive no pedido."""
        from apps.stores.services.checkout_service import CheckoutService
        pedido = CheckoutService.create_order(
            cart=self._carrinho(loja), customer_data=self._dados(),
            delivery_data={'method': 'pickup'}, indicado_por=INDICADOR,
        )
        assert pedido.metadata['indicado_por'] == INDICADOR


@pytest.mark.django_db
class TestConfigNoCardapio:
    """O cardápio decide qual card mostrar comparando os dois `enabled`."""

    def _config(self, loja):
        from apps.stores.api.views.storefront_views import (
            _cashback_program_payload, _loyalty_program_payload,
        )
        return _loyalty_program_payload(loja), _cashback_program_payload(loja)

    def test_cashback_ligado_aparece_na_config(self, loja):
        loja.metadata['cashback_percent'] = 3
        loja.save(update_fields=['metadata'])
        _, cb = self._config(loja)
        assert cb['enabled'] is True
        assert cb['percent'] == 3.0

    def test_loja_nova_nasce_com_cashback_DESLIGADO(self, db, dono):
        """A fidelidade tem default True por herança. O cashback não pode ter:
        toda loja do sistema estrearia prometendo dinheiro de volta."""
        nova = Store.objects.create(
            owner=dono, name='Nova', slug='nova-cb', store_type='food', status='active',
        )
        fid, cb = self._config(nova)
        assert cb['enabled'] is False
        assert fid['enabled'] is True

    def test_os_dois_programas_nunca_ligados_juntos_pelo_painel(self, loja):
        """O painel grava loyalty_enabled=False ao ligar o cashback."""
        loja.metadata['loyalty_enabled'] = False
        loja.save(update_fields=['metadata'])
        fid, cb = self._config(loja)
        assert cb['enabled'] is True
        assert fid['enabled'] is False
