"""Lote de correções 27/jul: cupom (campos mortos), cancelamento com estorno
e seleções de combo nos endpoints do cliente.

1. StoreCoupon.usage_limit_per_user era declarado e nunca verificado.
2. applicable_products/applicable_categories eram ignorados no desconto.
3. first_order_only não bloqueava checkout guest (user=None).
4. POST orders/{id}/cancel/ quebrava (TypeError notify_customer) e por isso
   nenhum cancelamento via API estornava estoque.
5. Endpoints do cliente (customer/orders) não expunham as escolhas do combo.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import (
    Store, StoreCategory, StoreCoupon, StoreOrder, StoreOrderItem, StoreProduct,
)
from apps.stores.models.order_combo_item import StoreOrderComboItem

User = get_user_model()


def _mk_store(owner, slug):
    return Store.objects.create(name=slug, slug=slug, owner=owner, status='active')


def _mk_coupon(store, **kw):
    now = timezone.now()
    defaults = dict(
        code='PROMO10',
        discount_type=StoreCoupon.DiscountType.PERCENTAGE,
        discount_value=Decimal('10'),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        is_active=True,
    )
    defaults.update(kw)
    return StoreCoupon.objects.create(store=store, **defaults)


def _mk_order(store, *, phone='63999990000', user=None, coupon_code='', status='delivered',
              payment_status='paid', total=Decimal('20')):
    return StoreOrder.objects.create(
        store=store,
        customer=user,
        customer_name='Cliente',
        customer_phone=phone,
        status=status,
        payment_status=payment_status,
        subtotal=total,
        total=total,
        coupon_code=coupon_code,
        delivery_method='pickup',
    )


class CouponPerUserLimitTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o1', email='o1@t.com', password='x')
        self.store = _mk_store(self.owner, 'loja-cupom-user')

    def test_limite_por_usuario_bloqueia_por_telefone(self):
        coupon = _mk_coupon(self.store, usage_limit_per_user=1)
        _mk_order(self.store, phone='63911112222', coupon_code='PROMO10')

        valid, msg = coupon.is_valid(subtotal=Decimal('50'), customer_phone='63911112222')
        self.assertFalse(valid)

        valid, _ = coupon.is_valid(subtotal=Decimal('50'), customer_phone='63933334444')
        self.assertTrue(valid)

    def test_limite_por_usuario_bloqueia_por_user(self):
        buyer = User.objects.create_user(username='b1', email='b1@t.com', password='x')
        coupon = _mk_coupon(self.store, usage_limit_per_user=2)
        _mk_order(self.store, user=buyer, coupon_code='promo10')
        _mk_order(self.store, user=buyer, coupon_code='PROMO10')

        valid, _ = coupon.is_valid(subtotal=Decimal('50'), user=buyer)
        self.assertFalse(valid)

    def test_pedido_cancelado_ou_pendente_nao_consome_limite(self):
        coupon = _mk_coupon(self.store, usage_limit_per_user=1)
        _mk_order(self.store, phone='63911112222', coupon_code='PROMO10',
                  status='cancelled', payment_status='pending')
        _mk_order(self.store, phone='63911112222', coupon_code='PROMO10',
                  status='pending', payment_status='pending')

        valid, _ = coupon.is_valid(subtotal=Decimal('50'), customer_phone='63911112222')
        self.assertTrue(valid)

    def test_sem_identidade_nao_bloqueia(self):
        coupon = _mk_coupon(self.store, usage_limit_per_user=1)
        valid, _ = coupon.is_valid(subtotal=Decimal('50'))
        self.assertTrue(valid)


class CouponFirstOrderGuestTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o2', email='o2@t.com', password='x')
        self.store = _mk_store(self.owner, 'loja-cupom-guest')
        self.coupon = _mk_coupon(self.store, first_order_only=True)

    def test_guest_com_pedido_anterior_pelo_telefone_e_bloqueado(self):
        _mk_order(self.store, phone='63955556666')
        valid, msg = self.coupon.is_valid(subtotal=Decimal('50'), customer_phone='63955556666')
        self.assertFalse(valid)
        self.assertIn('primeira compra', (msg or '').lower())

    def test_guest_sem_historico_passa(self):
        valid, _ = self.coupon.is_valid(subtotal=Decimal('50'), customer_phone='63977778888')
        self.assertTrue(valid)


class CouponScopeTests(APITestCase):
    """applicable_products/applicable_categories devem limitar a base do desconto."""

    def setUp(self):
        self.owner = User.objects.create_user(username='o3', email='o3@t.com', password='x')
        self.store = _mk_store(self.owner, 'loja-cupom-escopo')
        self.cat_bebidas = StoreCategory.objects.create(store=self.store, name='Bebidas', slug='bebidas')
        self.cat_pratos = StoreCategory.objects.create(store=self.store, name='Pratos', slug='pratos')
        self.suco = StoreProduct.objects.create(
            store=self.store, name='Suco', slug='suco', price=Decimal('10'),
            category=self.cat_bebidas)
        self.marmita = StoreProduct.objects.create(
            store=self.store, name='Marmita', slug='marmita', price=Decimal('30'),
            category=self.cat_pratos)

    def _items(self):
        return [
            {'product_id': str(self.suco.id), 'category_id': str(self.cat_bebidas.id),
             'total': Decimal('20')},   # 2x suco
            {'product_id': str(self.marmita.id), 'category_id': str(self.cat_pratos.id),
             'total': Decimal('30')},
        ]

    def test_percentual_por_produto_desconta_so_o_produto(self):
        coupon = _mk_coupon(self.store, applicable_products=[str(self.suco.id)])
        discount = coupon.calculate_discount(Decimal('50'), items=self._items())
        self.assertEqual(discount, Decimal('2.00'))  # 10% de 20, não de 50

    def test_percentual_por_categoria(self):
        coupon = _mk_coupon(self.store, applicable_categories=[str(self.cat_bebidas.id)])
        discount = coupon.calculate_discount(Decimal('50'), items=self._items())
        self.assertEqual(discount, Decimal('2.00'))

    def test_fixo_limitado_ao_subtotal_elegivel(self):
        coupon = _mk_coupon(
            self.store,
            discount_type=StoreCoupon.DiscountType.FIXED,
            discount_value=Decimal('25'),
            applicable_products=[str(self.suco.id)],
        )
        discount = coupon.calculate_discount(Decimal('50'), items=self._items())
        self.assertEqual(discount, Decimal('20.00'))  # cap no elegível, não nos 25

    def test_nenhum_item_elegivel_zera(self):
        coupon = _mk_coupon(self.store, applicable_categories=['id-inexistente'])
        discount = coupon.calculate_discount(Decimal('50'), items=self._items())
        self.assertEqual(discount, Decimal('0.00'))

    def test_sem_escopo_mantem_comportamento(self):
        coupon = _mk_coupon(self.store)
        discount = coupon.calculate_discount(Decimal('50'), items=self._items())
        self.assertEqual(discount, Decimal('5.00'))


class CancelOrderEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o4', email='o4@t.com', password='x')
        self.store = _mk_store(self.owner, 'loja-cancel')
        cat = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Marmita', slug='marmita-cancel', price=Decimal('20'),
            category=cat, track_stock=True, stock_quantity=8,
        )
        self.order = _mk_order(self.store, status='confirmed', payment_status='pending')
        StoreOrderItem.objects.create(
            order=self.order, product=self.product, product_name='Marmita',
            unit_price=Decimal('20'), quantity=2, subtotal=Decimal('40'),
        )
        self.client.force_authenticate(self.owner)

    def test_cancel_endpoint_cancela_e_estorna_estoque(self):
        url = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}/cancel/'
        resp = self.client.post(url, {'reason': 'cliente desistiu'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.product.stock_quantity, 10)  # 8 + 2 devolvidos


class CustomerOrderComboSelectionsTests(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username='o5', email='o5@t.com', password='x')
        self.store = _mk_store(owner, 'loja-combo-cliente')
        self.order = _mk_order(self.store)
        self.item = StoreOrderItem.objects.create(
            order=self.order, product=None, product_name='Combo Salada + Suco',
            unit_price=Decimal('35'), quantity=1, subtotal=Decimal('35'),
        )
        StoreOrderComboItem.objects.create(
            order=self.order, order_item=self.item, quantity=1,
            display_data={
                'combo_name': 'Combo Salada + Suco',
                'groups': [
                    {'group_name': 'Salada', 'items': [{'product_name': 'Caesar', 'quantity': 1}]},
                    {'group_name': 'Suco', 'items': [{'product_name': 'Laranja', 'quantity': 2}]},
                ],
            },
        )

    def test_detalhe_do_cliente_traz_escolhas_do_combo(self):
        url = f'/api/v1/stores/customer/orders/{self.order.id}/'
        resp = self.client.get(url, {'token': self.order.access_token})
        self.assertEqual(resp.status_code, 200, resp.content)

        items = resp.json()['items']
        self.assertEqual(len(items), 1)
        combo = items[0].get('combo_selections')
        self.assertIsNotNone(combo, 'item do combo deve expor combo_selections')
        self.assertEqual(combo[0]['group_name'], 'Salada')
        self.assertEqual(combo[0]['items'][0]['name'], 'Caesar')
        self.assertEqual(combo[1]['items'][0]['quantity'], 2)
