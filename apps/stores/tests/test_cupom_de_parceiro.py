"""Cupom de parceiro: quem divulga o código ganha % de cada venda dele.

O PEDIDO DO DONO (04/09): "quero criar os cupons com cashback, então vincular
um cupom — exemplo: cupom ACADEMIAFIT, vincular o cliente X, ele irá ganhar 3%
de cada compra do cupom".

É o modelo de parceria de bairro: a academia divulga o código para os alunos,
quem usa ganha desconto, e a academia acumula saldo na loja proporcional ao
que os alunos gastaram. Diferente da indicação pessoal (link com telefone), o
parceiro tem um CÓDIGO — que é ditável, cabe num cartaz e num story.

Metade disso já existia: `credit_referral` lê `coupon.metadata['owner_phone']`
desde a construção do cashback. Faltavam duas coisas para virar produto:

1. O PERCENTUAL POR CUPOM. Havia um percentual único da loja (5% de
   indicação), e parceria não se negocia assim: a academia com 400 alunos não
   leva o mesmo que o vizinho que indicou o irmão. Sem isso o dono teria que
   escolher um número só para todo mundo.

2. Uma tela para vincular. O campo existia e só era alcançável pelo shell de
   produção — que é onde se perde dinheiro sem rastro.

A REGRA DO DINHEIRO: o parceiro ganha sobre o que o cliente REALMENTE gastou,
já sem a entrega e sem o desconto do próprio cupom. Pagar percentual sobre o
frete é pagar comissão sobre o custo do motoboy.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot, StoreCoupon, StoreOrder
from apps.stores.services.cashback_service import CashbackService

User = get_user_model()


class CupomDeParceiroTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-parceiro', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-parceiro', owner=dono,
            store_type='food', status='active',
            metadata={'cashback_enabled': True},
        )
        self.academia = '5563999900011'

    def _cupom(self, code='ACADEMIAFIT', **metadata):
        return StoreCoupon.objects.create(
            store=self.store, code=code, discount_type='percentage',
            discount_value=Decimal('10'), is_active=True,
            valid_from=timezone.now() - timezone.timedelta(days=1),
            valid_until=timezone.now() + timezone.timedelta(days=365),
            metadata=metadata,
        )

    def _pedido(self, cupom, total='100.00', frete='0.00', desconto='0.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Aluna da academia',
            customer_phone='5563988877766',
            subtotal=Decimal(total), delivery_fee=Decimal(frete),
            discount=Decimal(desconto),
            total=Decimal(total) + Decimal(frete) - Decimal(desconto),
            status='delivered', payment_status='paid',
            coupon_code=cupom.code,
        )

    def _saldo(self):
        return CashbackService.balance(self.store, self.academia)

    # ── o que o dono pediu ──────────────────────────────────────────────

    def test_o_parceiro_ganha_o_percentual_do_cupom_dele(self):
        cupom = self._cupom(owner_phone=self.academia, owner_percent='3')

        CashbackService.credit_order(self._pedido(cupom, total='100.00'))

        assert self._saldo() == Decimal('3.00')

    def test_cada_parceiro_tem_o_proprio_percentual(self):
        """A academia com 400 alunos não leva o mesmo que o vizinho."""
        generoso = self._cupom('ACADEMIAFIT', owner_phone=self.academia, owner_percent='8')

        CashbackService.credit_order(self._pedido(generoso, total='100.00'))

        assert self._saldo() == Decimal('8.00')

    def test_sem_percentual_proprio_usa_o_da_loja(self):
        """Vincular o parceiro sem definir a taxa não pode zerar o crédito."""
        cupom = self._cupom(owner_phone=self.academia)

        CashbackService.credit_order(self._pedido(cupom, total='100.00'))

        assert self._saldo() == Decimal('5.00')  # o padrão da loja

    def test_cupom_sem_parceiro_nao_credita_ninguem(self):
        """A maioria dos cupons é promoção da loja, não parceria."""
        CashbackService.credit_order(self._pedido(self._cupom()))

        assert StoreCashbackLot.objects.filter(
            store=self.store, origin=StoreCashbackLot.Origin.REFERRAL,
        ).count() == 0

    # ── a base do cálculo ───────────────────────────────────────────────

    def test_a_entrega_fica_de_fora(self):
        """Comissão sobre o frete é comissão sobre o custo do motoboy."""
        cupom = self._cupom(owner_phone=self.academia, owner_percent='10')

        CashbackService.credit_order(self._pedido(cupom, total='100.00', frete='15.00'))

        assert self._saldo() == Decimal('10.00')

    def test_o_desconto_do_proprio_cupom_fica_de_fora(self):
        """O parceiro ganha sobre o que ENTROU, não sobre a etiqueta."""
        cupom = self._cupom(owner_phone=self.academia, owner_percent='10')

        # R$ 100 com 10% de desconto: entraram R$ 90.
        CashbackService.credit_order(self._pedido(cupom, total='100.00', desconto='10.00'))

        assert self._saldo() == Decimal('9.00')

    # ── o que protege o dono ────────────────────────────────────────────

    def test_o_parceiro_usando_o_proprio_cupom_nao_ganha_comissao(self):
        """Auto-indicação é desconto, não parceria.

        Ele CONTINUA ganhando o cashback normal de compra — é cliente como
        qualquer outro. O que não pode existir é a comissão: senão o parceiro
        compra com o próprio código e a loja paga duas vezes na mesma venda.
        """
        cupom = self._cupom(owner_phone=self.academia, owner_percent='3')
        pedido = self._pedido(cupom)
        pedido.customer_phone = self.academia
        pedido.save(update_fields=['customer_phone'])

        CashbackService.credit_order(pedido)

        assert not StoreCashbackLot.objects.filter(
            store=self.store, origin=StoreCashbackLot.Origin.REFERRAL,
        ).exists()

    def test_percentual_invalido_nao_derruba_o_pedido(self):
        """Texto no campo de porcentagem não pode impedir a venda de fechar."""
        cupom = self._cupom(owner_phone=self.academia, owner_percent='três por cento')

        CashbackService.credit_order(self._pedido(cupom, total='100.00'))

        assert self._saldo() == Decimal('5.00')  # cai no padrão da loja

    def test_um_credito_por_pedido_mesmo_com_link_e_cupom(self):
        """Link de indicação E cupom de parceiro no mesmo pedido = 1 crédito.

        Dois créditos de indicação na mesma venda é a loja pagando duas vezes.
        """
        cupom = self._cupom(owner_phone=self.academia, owner_percent='3')
        pedido = self._pedido(cupom, total='100.00')
        pedido.metadata = {'indicado_por': '5563911112222'}
        pedido.save(update_fields=['metadata'])

        CashbackService.credit_order(pedido)

        assert StoreCashbackLot.objects.filter(
            store=self.store, origin=StoreCashbackLot.Origin.REFERRAL,
        ).count() == 1
