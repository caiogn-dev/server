"""Cartão na maquininha (01/10): "pagar na entrega" deixa de ser sempre dinheiro.

Antes, quem pagava no cartão na maquininha do entregador era gravado como
`cash` — e o caixa e os relatórios contavam essa venda como dinheiro na gaveta.
Agora é `card_on_delivery`: paga na entrega como o dinheiro (liquida ao
entregar), mas NÃO entra no dinheiro esperado do caixa.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores import formas_de_pagamento as formas
from apps.stores.api.serializers import CheckoutSerializer
from apps.stores.api.views.storefront_views import build_store_payment_config
from apps.stores.models import Store, StoreCashSession, StoreOrder
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class CartaoNaMaquininhaTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-maq', email='o-maq@real.com', password='x')
        self.store = Store.objects.create(name='Loja Maq', slug='loja-maq', owner=self.owner, status='active')

    def _order(self, metodo='', total='40.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            customer_email='c@real.com', subtotal=Decimal(total), total=Decimal(total),
            payment_method=metodo,
        )

    def test_checkout_aceita_e_grava_card_on_delivery_pendente(self):
        assert CheckoutSerializer().fields['payment_method'].choices.get('card_on_delivery') is not None
        order = self._order()
        r = CheckoutService.create_payment(order=order, payment_method='card_on_delivery')
        order.refresh_from_db()
        assert r['success'] is True
        assert order.payment_method == 'card_on_delivery'
        assert order.payment_status == StoreOrder.PaymentStatus.PENDING

    def test_entregue_na_maquininha_vira_pago(self):
        order = self._order('card_on_delivery')
        order.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        order.refresh_from_db()
        assert order.payment_status == StoreOrder.PaymentStatus.PAID

    def test_caixa_espera_so_o_dinheiro_nao_a_maquininha(self):
        sessao = StoreCashSession.objects.create(
            store=self.store, opened_by=self.owner, opening_amount=Decimal('100.00'),
        )
        agora = timezone.now()
        for metodo, total in (('cash', '30.00'), ('card_on_delivery', '50.00')):
            o = self._order(metodo, total)
            StoreOrder.objects.filter(pk=o.pk).update(
                payment_status=StoreOrder.PaymentStatus.PAID, paid_at=agora,
                status=StoreOrder.OrderStatus.DELIVERED,
            )
        assert sessao.expected_cash() == Decimal('130.00')

    def test_loja_anuncia_a_maquininha_junto_com_o_dinheiro(self):
        assert 'card_on_delivery' in build_store_payment_config(self.store)['enabled_methods']
        self.store.metadata = {**(self.store.metadata or {}), 'cash_enabled': False}
        self.store.save(update_fields=['metadata'])
        metodos = build_store_payment_config(self.store)['enabled_methods']
        assert 'cash' not in metodos and 'card_on_delivery' not in metodos


class CatalogoDeFormasTests(APITestCase):
    def test_um_nome_para_cada_metodo_gravado(self):
        for valor in ('pix', 'card', 'credit_card', 'debit_card', 'cash', 'card_on_delivery',
                      'voucher', 'voucher_link', 'link', 'other'):
            assert formas.rotulo(valor) and formas.rotulo(valor) != valor, valor
        assert formas.rotulo('card_on_delivery') == 'Cartão na maquininha'
        assert formas.rotulo('voucher') == 'Vale-refeição'

    def test_pagos_na_entrega(self):
        assert formas.PAGOS_NA_ENTREGA == frozenset({'cash', 'card_on_delivery'})

    def test_relatorio_e_nota_conhecem_a_maquininha(self):
        from apps.fiscal.services import FORMA_PAGAMENTO
        from apps.stores.services.exports.relatorios import _ROTULO_PAGAMENTO
        assert _ROTULO_PAGAMENTO['card_on_delivery'] == 'Cartão na maquininha'
        assert _ROTULO_PAGAMENTO['voucher'] == 'Vale-refeição'
        assert FORMA_PAGAMENTO['card_on_delivery'][0] == '99'
