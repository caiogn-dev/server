from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCategory, StoreCustomer, StoreOrder, StoreProduct
from apps.automation.models import CompanyProfile, CustomerSession


User = get_user_model()


class DashboardOrderCreateContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user('order-owner', 'order-owner@example.com', 'pass')
        self.client.force_authenticate(user=self.owner)
        self.store = Store.objects.create(
            owner=self.owner,
            name='Order Store',
            slug='order-store',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            is_active=True,
        )
        self.category = StoreCategory.objects.create(store=self.store, name='Pratos', slug='pratos')
        self.product = StoreProduct.objects.create(
            store=self.store,
            category=self.category,
            name='Salada',
            slug='salada',
            price=Decimal('25.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
        )

    def _payload(self, **overrides):
        payload = {
            'store': str(self.store.id),
            'customer_name': 'Ana',
            'customer_phone': '556399999999',
            'items': [{'product_id': str(self.product.id), 'quantity': 1}],
            'delivery_method': 'delivery',
            'delivery_address': {'street': 'Quadra 203 Sul', 'city': 'Palmas', 'state': 'TO'},
            'delivery_fee': '5.00',
        }
        payload.update(overrides)
        return payload

    def test_rejects_negative_delivery_fee(self):
        response = self.client.post(
            '/api/v1/stores/orders/',
            self._payload(delivery_fee='-1.00'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('delivery_fee', response.data['error']['details'])

    def test_manual_delivery_fee_is_audited_in_metadata(self):
        response = self.client.post(
            '/api/v1/stores/orders/',
            self._payload(adjustment_reason='Pedido feito pelo operador'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = StoreOrder.objects.get(id=response.data['id'])
        self.assertEqual(order.metadata['manual_delivery_fee']['amount'], '5.00')
        self.assertEqual(order.metadata['manual_delivery_fee']['reason'], 'Pedido feito pelo operador')
        self.assertEqual(order.metadata['manual_delivery_fee']['user_id'], str(self.owner.id))

    def test_manual_order_create_links_order_to_customer_identity_not_staff_user(self):
        response = self.client.post(
            '/api/v1/stores/orders/',
            self._payload(customer_name='Dyessika Rayanne', customer_phone='556384354052'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = StoreOrder.objects.get(id=response.data['id'])
        store_customer = StoreCustomer.objects.get(store=self.store, phone='556384354052')
        self.assertEqual(order.customer_id, store_customer.user_id)
        self.assertNotEqual(order.customer_id, self.owner.id)
        self.assertEqual(order.metadata['customer']['store_customer_id'], str(store_customer.id))

    def test_manual_payment_patch_sets_paid_at_without_status_automessage(self):
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Dyessika',
            customer_phone='556384354052',
            customer_email='',
            status=StoreOrder.OrderStatus.OUT_FOR_DELIVERY,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=Decimal('25.00'),
            delivery_fee=Decimal('5.00'),
            total=Decimal('30.00'),
            delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
        )

        with patch('apps.whatsapp.tasks.automation_tasks.notify_order_status_change') as mock_task, \
             patch('apps.automation.signals.transaction.on_commit', side_effect=lambda fn: fn()):
            response = self.client.patch(
                f'/api/v1/stores/orders/{order.id}/',
                {'payment_status': StoreOrder.PaymentStatus.PAID},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(order.metadata['manual_payment']['source'], 'dashboard')
        self.assertEqual(order.metadata['manual_payment']['user_id'], str(self.owner.id))
        mock_task.delay.assert_not_called()

    def test_paid_order_updates_linked_customer_session(self):
        profile = CompanyProfile.objects.get(store=self.store)
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Dyessika Rayanne',
            customer_phone='556384354052',
            customer_email='dyessika@test.com',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=Decimal('40.67'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('40.67'),
            delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
        )
        session = CustomerSession.objects.create(
            company=profile,
            phone_number='556384354052',
            session_id='dyessika-session',
            status=CustomerSession.SessionStatus.PAYMENT_PENDING,
            cart_total=Decimal('40.67'),
            cart_items_count=1,
            order=order,
            external_order_id=order.order_number,
            payment_id=str(order.id),
        )

        response = self.client.patch(
            f'/api/v1/stores/orders/{order.id}/',
            {'payment_status': StoreOrder.PaymentStatus.PAID},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.status, CustomerSession.SessionStatus.PAYMENT_CONFIRMED)
        self.assertEqual(session.customer_name, 'Dyessika Rayanne')
