"""Novo pedido do painel (28/10): cupom conferido, troco, vale na entrega e fiado.

Antes: o cupom era gravado cru (sem conferir nem descontar), o troco não tinha
como entrar, o vale não existia e o fiado ia como `cash` + nota — ao entregar,
dinheiro é liquidado e o fiado aparecia como RECEBIDO no caixa.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreCoupon, StoreOrder, StoreProduct

User = get_user_model()


class NovoPedidoPagamentoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-np', email='np@x.com', password='x')
        self.store = Store.objects.create(name='Loja NP', slug='loja-np', owner=self.owner, status='active')
        cat = StoreCategory.objects.create(store=self.store, name='Pratos', slug='pratos')
        self.produto = StoreProduct.objects.create(store=self.store, name='Prato', price=40, track_stock=False, category=cat)
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def criar(self, **extra):
        payload = {
            'store': str(self.store.id), 'customer_name': 'Ana', 'customer_phone': '5563999990001',
            'delivery_method': 'pickup', 'payment_method': 'cash', 'source': 'dashboard',
            'items': [{'product_id': str(self.produto.id), 'quantity': 1}],
        }
        payload.update(extra)
        r = self.client.post(self.url, payload, format='json')
        return r

    def cupom(self, **campos):
        agora = timezone.now()
        dados = dict(store=self.store, code='VOLTA10', discount_type='percentage', discount_value=Decimal('10'),
                     valid_from=agora - timedelta(days=1), valid_until=agora + timedelta(days=30), usage_limit=100)
        dados.update(campos)
        return StoreCoupon.objects.create(**dados)

    def test_cupom_valido_desconta_e_registra_o_uso(self):
        c = self.cupom()
        r = self.criar(coupon_code='volta10')
        self.assertEqual(r.status_code, 201, r.content)
        pedido = StoreOrder.objects.get(id=r.data['id'])
        self.assertEqual(pedido.coupon_code, 'VOLTA10')
        self.assertEqual(pedido.discount, Decimal('4.00'))
        self.assertEqual(pedido.total, Decimal('36.00'))
        c.refresh_from_db()
        self.assertEqual(c.used_count, 1)

    def test_cupom_invalido_recusa_o_pedido(self):
        r = self.criar(coupon_code='NAOEXISTE')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(StoreOrder.objects.exists())

    def test_cupom_soma_ao_desconto_manual(self):
        self.cupom()
        r = self.criar(coupon_code='VOLTA10', discount=5)
        self.assertEqual(StoreOrder.objects.get(id=r.data['id']).discount, Decimal('9.00'))

    def test_dinheiro_guarda_o_troco(self):
        r = self.criar(change_for=50)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(StoreOrder.objects.get(id=r.data['id']).change_for, Decimal('50.00'))

    def test_vale_na_entrega_guarda_a_bandeira_e_liquida_ao_entregar(self):
        r = self.criar(payment_method='voucher_on_delivery', voucher_brand='alelo')
        self.assertEqual(r.status_code, 201, r.content)
        pedido = StoreOrder.objects.get(id=r.data['id'])
        self.assertEqual(pedido.payment_method, 'voucher_on_delivery')
        self.assertEqual(pedido.metadata.get('voucher_brand'), 'alelo')
        pedido.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_fiado_nao_vira_pago_ao_entregar(self):
        r = self.criar(payment_method='fiado')
        pedido = StoreOrder.objects.get(id=r.data['id'])
        self.assertEqual(pedido.payment_method, 'fiado')
        pedido.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        self.assertNotEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_rotulos(self):
        from apps.stores.formas_de_pagamento import rotulo
        self.assertEqual(rotulo('voucher_on_delivery'), 'Vale na entrega')
        self.assertEqual(rotulo('fiado'), 'Fiado (a receber)')

    def test_nota_fiscal_conhece_vale_e_fiado(self):
        from apps.fiscal.services import FORMA_PAGAMENTO
        self.assertEqual(FORMA_PAGAMENTO['voucher_on_delivery'][0], '99')
        self.assertEqual(FORMA_PAGAMENTO['fiado'][0], '05')
