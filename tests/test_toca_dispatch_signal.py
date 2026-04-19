from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class TocaDispatchSignalTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='toca_signal_owner',
            email='toca-signal@example.com',
            password='pass123',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='CE Saladas',
            slug='ce-saladas-signal',
            status='active',
            metadata={'delivery_provider': 'toca'},
            default_delivery_fee=Decimal('8.00'),
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Cliente Teste',
            customer_phone='63999990000',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
            delivery_address={
                'street': 'Rua Teste',
                'number': '10',
                'neighborhood': 'Centro',
                'city': 'Palmas',
                'state': 'TO',
            },
            subtotal=Decimal('32.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            delivery_fee=Decimal('8.00'),
            total=Decimal('40.00'),
        )

    @override_settings(TOCA_DELIVERY_ENABLED=False)
    @patch('apps.stores.tasks.dispatch_order_to_toca_delivery.delay')
    def test_enqueues_toca_dispatch_when_order_becomes_confirmed(self, mock_delay):
        self.order.status = StoreOrder.OrderStatus.CONFIRMED
        self.order.save(update_fields=['status', 'updated_at'])

        mock_delay.assert_called_once_with(str(self.order.id))
