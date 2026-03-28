"""
Unit tests for CheckoutService.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreOrder,
    StoreProduct, StoreDeliveryZone, StoreCoupon,
)
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


def _make_store(owner, slug='test-store'):
    return Store.objects.create(
        owner=owner,
        name='Test Store',
        slug=slug,
        is_active=True,
        default_delivery_fee=Decimal('8.00'),
    )


def _make_product(store, name='Produto', price=Decimal('25.00')):
    return StoreProduct.objects.create(
        store=store,
        name=name,
        price=price,
        status=StoreProduct.ProductStatus.ACTIVE,
        track_stock=False,
    )


class CheckoutNormalizeBaseUrlTest(TestCase):
    """Tests for _normalize_base_url helper."""

    def test_valid_http_url(self):
        result = CheckoutService._normalize_base_url('http://example.com/path/page')
        self.assertEqual(result, 'http://example.com')

    def test_valid_https_url(self):
        result = CheckoutService._normalize_base_url('https://shop.mystore.com.br/')
        self.assertEqual(result, 'https://shop.mystore.com.br')

    def test_url_without_scheme(self):
        result = CheckoutService._normalize_base_url('mystore.com.br')
        self.assertEqual(result, 'https://mystore.com.br')

    def test_protocol_relative_url(self):
        result = CheckoutService._normalize_base_url('//example.com')
        self.assertEqual(result, 'https://example.com')

    def test_empty_string(self):
        result = CheckoutService._normalize_base_url('')
        self.assertEqual(result, '')

    def test_none_value(self):
        result = CheckoutService._normalize_base_url(None)
        self.assertEqual(result, '')


class CheckoutDeliveryFeeTest(TestCase):
    """Tests for calculate_delivery_fee."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='store_owner', email='owner@test.com', password='pass'
        )
        self.store = _make_store(self.owner)

    def test_no_distance_returns_base_fee(self):
        result = CheckoutService.calculate_delivery_fee(self.store, distance_km=None)
        self.assertIn('fee', result)
        self.assertEqual(result['fee'], float(self.store.default_delivery_fee))

    def test_short_distance_uses_base_fee(self):
        result = CheckoutService.calculate_delivery_fee(self.store, distance_km=Decimal('2.0'))
        self.assertIn('fee', result)
        # Within free_km_threshold (default 3km), should return base fee
        self.assertGreater(result['fee'], 0)

    def test_longer_distance_increases_fee(self):
        short = CheckoutService.calculate_delivery_fee(self.store, distance_km=Decimal('2.0'))
        long_ = CheckoutService.calculate_delivery_fee(self.store, distance_km=Decimal('10.0'))
        self.assertGreater(long_['fee'], short['fee'])

    def test_configured_zone_takes_priority(self):
        zone = StoreDeliveryZone.objects.create(
            store=self.store,
            name='Zona Proxima',
            zone_type='custom_distance',
            min_km=Decimal('0'),
            max_km=Decimal('5'),
            delivery_fee=Decimal('5.00'),
            is_active=True,
        )
        result = CheckoutService.calculate_delivery_fee(self.store, distance_km=Decimal('3.0'))
        self.assertEqual(result['fee'], 5.0)
        self.assertEqual(result['zone_id'], str(zone.id))

    def test_fee_capped_at_max(self):
        # Very far distance, should cap at max_fee (default 25.00)
        result = CheckoutService.calculate_delivery_fee(self.store, distance_km=Decimal('50.0'))
        self.assertLessEqual(result['fee'], 25.0)


class CheckoutCouponValidationTest(TestCase):
    """Tests for validate_coupon."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='coupon_owner', email='coupon@test.com', password='pass'
        )
        self.store = _make_store(self.owner, slug='coupon-store')

    def test_valid_coupon_returns_discount(self):
        coupon = StoreCoupon.objects.create(
            store=self.store,
            code='DESCONTO10',
            discount_type=StoreCoupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10'),
            is_active=True,
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=365),
        )
        result = CheckoutService.validate_coupon(self.store, 'DESCONTO10', subtotal=Decimal('100'))
        self.assertTrue(result['valid'])
        self.assertAlmostEqual(result['discount'], 10.0)

    def test_invalid_coupon_code(self):
        result = CheckoutService.validate_coupon(self.store, 'INVALIDO', subtotal=Decimal('100'))
        self.assertFalse(result['valid'])
        self.assertIn('error', result)

    def test_coupon_from_other_store_not_found(self):
        other_owner = User.objects.create_user(
            username='other_owner2', email='other2@test.com', password='pass'
        )
        other_store = _make_store(other_owner, slug='other-store2')
        StoreCoupon.objects.create(
            store=other_store,
            code='OUTRO10',
            discount_type=StoreCoupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10'),
            is_active=True,
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=365),
        )
        result = CheckoutService.validate_coupon(self.store, 'OUTRO10', subtotal=Decimal('100'))
        self.assertFalse(result['valid'])

    def test_inactive_coupon_not_valid(self):
        StoreCoupon.objects.create(
            store=self.store,
            code='INATIVO',
            discount_type=StoreCoupon.DiscountType.PERCENTAGE,
            discount_value=Decimal('10'),
            is_active=False,
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=365),
        )
        result = CheckoutService.validate_coupon(self.store, 'INATIVO', subtotal=Decimal('100'))
        self.assertFalse(result['valid'])


class CheckoutCreateOrderTest(TestCase):
    """Tests for create_order."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='order_owner', email='order@test.com', password='pass'
        )
        self.customer = User.objects.create_user(
            username='customer', email='customer@test.com', password='pass'
        )
        self.store = _make_store(self.owner, slug='order-store')
        self.product = _make_product(self.store)

    def _make_cart_with_item(self):
        cart = StoreCart.objects.create(store=self.store, user=self.customer)
        StoreCartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=2,
        )
        return cart

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_create_order_success(self, mock_email):
        cart = self._make_cart_with_item()
        customer_data = {
            'name': 'João Silva',
            'email': 'joao@test.com',
            'phone': '+5511999998888',
        }
        order = CheckoutService.create_order(cart, customer_data)
        self.assertIsNotNone(order.pk)
        self.assertEqual(order.store, self.store)
        self.assertEqual(order.status, StoreOrder.OrderStatus.PENDING)
        self.assertGreater(order.total, 0)
        mock_email.assert_called_once_with(order, 'order_received')

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_create_order_clears_cart(self, _mock_email):
        cart = self._make_cart_with_item()
        customer_data = {'name': 'Ana', 'email': 'ana@test.com', 'phone': '+5511888887777'}
        CheckoutService.create_order(cart, customer_data)
        cart.refresh_from_db()
        self.assertFalse(cart.is_active)

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_create_order_with_delivery(self, _mock_email):
        cart = self._make_cart_with_item()
        customer_data = {'name': 'Carlos', 'email': 'carlos@test.com', 'phone': '+5511777776666'}
        delivery_data = {
            'method': 'delivery',
            'distance_km': '3.5',
            'address': {
                'street': 'Rua Teste',
                'number': '100',
                'city': 'São Paulo',
                'state': 'SP',
                'zip_code': '01310000',
            },
        }
        order = CheckoutService.create_order(cart, customer_data, delivery_data=delivery_data)
        self.assertEqual(order.delivery_method, StoreOrder.DeliveryMethod.DELIVERY)
        self.assertGreater(order.delivery_fee, 0)

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_create_order_with_coupon(self, _mock_email):
        coupon = StoreCoupon.objects.create(
            store=self.store,
            code='FLAT5',
            discount_type=StoreCoupon.DiscountType.FIXED,
            discount_value=Decimal('5.00'),
            is_active=True,
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=365),
        )
        cart = self._make_cart_with_item()
        customer_data = {'name': 'Bia', 'email': 'bia@test.com', 'phone': '+5511666665555'}
        order = CheckoutService.create_order(cart, customer_data, coupon_code='FLAT5')
        self.assertEqual(order.discount, Decimal('5.00'))
        self.assertEqual(order.coupon_code, 'FLAT5')


class CheckoutProcessWebhookTest(TestCase):
    """Tests for process_payment_webhook."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='webhook_owner', email='wh@test.com', password='pass'
        )
        self.store = _make_store(self.owner, slug='webhook-store')

    def _make_order(self, payment_id='pay_001'):
        return StoreOrder.objects.create(
            store=self.store,
            payment_id=payment_id,
            status=StoreOrder.OrderStatus.PROCESSING,
            payment_status=StoreOrder.PaymentStatus.PROCESSING,
            subtotal=Decimal('50'),
            total=Decimal('50'),
            delivery_fee=Decimal('0'),
            discount=Decimal('0'),
            tax=Decimal('0'),
        )

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_approved_payment_marks_order_paid(self, _mock_email):
        order = self._make_order('pay_approved')
        result = CheckoutService.process_payment_webhook('pay_approved', 'approved')
        result.refresh_from_db()
        self.assertEqual(result.status, StoreOrder.OrderStatus.PAID)
        self.assertEqual(result.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(result.paid_at)

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    def test_rejected_payment_marks_order_failed(self, _mock_email):
        order = self._make_order('pay_rejected')
        result = CheckoutService.process_payment_webhook('pay_rejected', 'rejected')
        result.refresh_from_db()
        self.assertEqual(result.status, StoreOrder.OrderStatus.FAILED)

    def test_unknown_payment_id_returns_none(self):
        result = CheckoutService.process_payment_webhook('nonexistent_pay', 'approved')
        self.assertIsNone(result)
