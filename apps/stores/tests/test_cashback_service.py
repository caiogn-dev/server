"""Cashback por telefone: crédito, indicação, resgate e vencimento.

O erro que estes testes existem para impedir é o da fidelidade antiga:
creditar só quem está logado. O checkout é guest-first — se o crédito exigir
`user`, o programa nasce vazio.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreCoupon, StoreOrder
from apps.stores.services.cashback_service import CashbackService


@pytest.fixture
def dono(db):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.create_user(
        username='dono-cashback', email='dono-cashback@teste.local', password='x',
    )


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Loja Teste', slug='loja-teste', store_type='food',
        status='active', metadata={'cashback_enabled': True},
    )


def _pedido(loja, total, phone='5563999547790', **kw):
    return StoreOrder.objects.create(
        store=loja, customer_name='Cliente', customer_phone=phone,
        total=Decimal(str(total)), subtotal=Decimal(str(total)),
        payment_status='paid', **kw,
    )


@pytest.mark.django_db
class TestCreditoDeCompra:
    def test_credita_3_porcento_do_pedido_pago(self, loja):
        pedido = _pedido(loja, '100.00')
        CashbackService.credit_purchase(pedido)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('3.00')

    def test_credita_pedido_de_convidado_sem_usuario(self, loja):
        """O buraco da fidelidade antiga: sem `customer` ninguém era creditado."""
        pedido = _pedido(loja, '72.00')
        assert pedido.customer_id is None
        CashbackService.credit_purchase(pedido)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('2.16')

    def test_credito_e_idempotente_por_pedido(self, loja):
        """Webhook do MP reenvia notificação; creditar duas vezes dobra o saldo."""
        pedido = _pedido(loja, '100.00')
        CashbackService.credit_purchase(pedido)
        CashbackService.credit_purchase(pedido)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('3.00')

    def test_telefone_sem_nono_digito_e_o_mesmo_cliente(self, loja):
        """O wa_id do WhatsApp vem sem o nono dígito; o site grava com ele."""
        CashbackService.credit_purchase(_pedido(loja, '100.00', phone='5563999547790'))
        assert CashbackService.balance(loja, '556399547790', verificado=True) == Decimal('3.00')

    def test_pedido_nao_pago_nao_credita(self, loja):
        pedido = _pedido(loja, '100.00')
        pedido.payment_status = 'pending'
        pedido.save(update_fields=['payment_status'])
        CashbackService.credit_purchase(pedido)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('0.00')

    def test_loja_com_cashback_desligado_nao_credita(self, db, dono):
        loja = Store.objects.create(owner=dono, name='X', slug='x', store_type='food', status='active')
        CashbackService.credit_purchase(_pedido(loja, '100.00'))
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('0.00')

    def test_percentual_da_loja_manda(self, loja):
        loja.metadata['cashback_percent'] = 10
        loja.save(update_fields=['metadata'])
        CashbackService.credit_purchase(_pedido(loja, '100.00'))
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('10.00')

    def test_pedido_sem_telefone_nao_quebra(self, loja):
        CashbackService.credit_purchase(_pedido(loja, '100.00', phone=''))
        assert StoreCashbackLot.objects.count() == 0


@pytest.mark.django_db
class TestCreditoDeIndicacao:
    def _cupom(self, loja, code='NUTRI.MARI', dono='5563988887777'):
        agora = timezone.now()
        return StoreCoupon.objects.create(
            store=loja, code=code, discount_type='percentage', discount_value=5,
            valid_from=agora, valid_until=agora + timedelta(days=365),
            metadata={'owner_phone': dono},
        )

    def test_dono_do_cupom_ganha_5_porcento_da_venda(self, loja):
        cupom = self._cupom(loja)
        pedido = _pedido(loja, '90.00', coupon_code='NUTRI.MARI')
        CashbackService.credit_referral(pedido, cupom)
        assert CashbackService.balance(loja, '5563988887777', verificado=True) == Decimal('4.50')

    def test_indicacao_nao_mexe_no_saldo_de_quem_comprou(self, loja):
        cupom = self._cupom(loja)
        pedido = _pedido(loja, '90.00', coupon_code='NUTRI.MARI')
        CashbackService.credit_referral(pedido, cupom)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('0.00')

    def test_cupom_sem_dono_nao_credita_ninguem(self, loja):
        agora = timezone.now()
        cupom = StoreCoupon.objects.create(
            store=loja, code='SALADA10', discount_type='percentage', discount_value=10,
            valid_from=agora, valid_until=agora + timedelta(days=30),
        )
        CashbackService.credit_referral(_pedido(loja, '90.00'), cupom)
        assert StoreCashbackLot.objects.count() == 0

    def test_auto_indicacao_nao_premia(self, loja):
        """Dono usando o próprio cupom é desconto, não indicação."""
        cupom = self._cupom(loja, dono='5563999547790')
        CashbackService.credit_referral(_pedido(loja, '90.00'), cupom)
        assert StoreCashbackLot.objects.count() == 0

    def test_indicacao_e_compra_convivem_no_mesmo_pedido(self, loja):
        cupom = self._cupom(loja)
        pedido = _pedido(loja, '100.00', coupon_code='NUTRI.MARI')
        CashbackService.credit_purchase(pedido)
        CashbackService.credit_referral(pedido, cupom)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('3.00')
        assert CashbackService.balance(loja, '5563988887777', verificado=True) == Decimal('5.00')


@pytest.mark.django_db
class TestResgate:
    def test_resgate_abate_do_saldo(self, loja):
        CashbackService.credit_purchase(_pedido(loja, '1000.00'))
        pedido = _pedido(loja, '50.00')
        assert CashbackService.redeem(loja, '5563999547790', pedido, Decimal('20.00'), verificado=True) == Decimal('20.00')
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('10.00')

    def test_resgate_nunca_passa_do_saldo(self, loja):
        CashbackService.credit_purchase(_pedido(loja, '100.00'))
        pedido = _pedido(loja, '50.00')
        assert CashbackService.redeem(loja, '5563999547790', pedido, Decimal('99.00'), verificado=True) == Decimal('3.00')
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('0.00')

    def test_resgate_e_idempotente_por_pedido(self, loja):
        CashbackService.credit_purchase(_pedido(loja, '1000.00'))
        pedido = _pedido(loja, '50.00')
        CashbackService.redeem(loja, '5563999547790', pedido, Decimal('10.00'), verificado=True)
        CashbackService.redeem(loja, '5563999547790', pedido, Decimal('10.00'), verificado=True)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('20.00')

    def test_consome_o_lote_que_vence_primeiro(self, loja):
        agora = timezone.now()
        for dias, valor in ((5, '10.00'), (90, '10.00')):
            StoreCashbackLot.objects.create(
                store=loja, phone='5563999547790', amount=Decimal(valor),
                remaining=Decimal(valor), expires_at=agora + timedelta(days=dias),
            )
        CashbackService.redeem(loja, '5563999547790', _pedido(loja, '50.00'), Decimal('10.00'), verificado=True)
        vivos = StoreCashbackLot.objects.filter(remaining__gt=0)
        assert vivos.count() == 1
        assert (vivos.first().expires_at - agora).days >= 89


@pytest.mark.django_db
class TestVencimento:
    def test_lote_vencido_nao_conta_no_saldo(self, loja):
        StoreCashbackLot.objects.create(
            store=loja, phone='5563999547790', amount=Decimal('10.00'),
            remaining=Decimal('10.00'), expires_at=timezone.now() - timedelta(days=1),
        )
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('0.00')

    def test_credito_vence_em_60_dias_por_padrao(self, loja):
        CashbackService.credit_purchase(_pedido(loja, '100.00'))
        lote = StoreCashbackLot.objects.get()
        assert 59 <= (lote.expires_at - timezone.now()).days <= 60

    def test_prazo_da_loja_manda(self, loja):
        loja.metadata['cashback_expiry_days'] = 30
        loja.save(update_fields=['metadata'])
        CashbackService.credit_purchase(_pedido(loja, '100.00'))
        lote = StoreCashbackLot.objects.get()
        assert 29 <= (lote.expires_at - timezone.now()).days <= 30


@pytest.mark.django_db
class TestCreditOrder:
    """`credit_order` é o ÚNICO gancho: roda quando o pedido vira pago.

    A indicação não pode ser creditada no checkout (o pedido ainda não foi
    pago e pode ser cancelado); o cupom usado fica gravado em
    order.coupon_code e é relido aqui.
    """

    def test_credita_compra_e_indicacao_de_uma_vez(self, loja):
        agora = timezone.now()
        StoreCoupon.objects.create(
            store=loja, code='NUTRI.MARI', discount_type='percentage', discount_value=5,
            valid_from=agora, valid_until=agora + timedelta(days=365),
            metadata={'owner_phone': '5563988887777'},
        )
        pedido = _pedido(loja, '100.00', coupon_code='NUTRI.MARI')
        CashbackService.credit_order(pedido)
        assert CashbackService.balance(loja, '5563999547790', verificado=True) == Decimal('3.00')
        assert CashbackService.balance(loja, '5563988887777', verificado=True) == Decimal('5.00')

    def test_sem_cupom_credita_so_a_compra(self, loja):
        CashbackService.credit_order(_pedido(loja, '100.00'))
        assert StoreCashbackLot.objects.count() == 1

    def test_cupom_de_outra_loja_nao_credita(self, loja, dono):
        outra = Store.objects.create(
            owner=dono, name='Outra', slug='outra', store_type='food', status='active',
        )
        agora = timezone.now()
        StoreCoupon.objects.create(
            store=outra, code='NUTRI.MARI', discount_type='percentage', discount_value=5,
            valid_from=agora, valid_until=agora + timedelta(days=365),
            metadata={'owner_phone': '5563988887777'},
        )
        CashbackService.credit_order(_pedido(loja, '100.00', coupon_code='NUTRI.MARI'))
        assert CashbackService.balance(loja, '5563988887777', verificado=True) == Decimal('0.00')

    def test_nunca_levanta_excecao(self, loja):
        """Roda dentro da transição de status do pedido: quebrar aqui é
        deixar o pedido pago sem confirmar."""
        CashbackService.credit_order(None)
