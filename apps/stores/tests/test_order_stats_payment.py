"""Stats de pedidos: contagem e receita por payment_status (usado no painel de pagamentos)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class OrderStatsPaymentStatusTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-stats', email='ow-stats@t.com', password='x')
        self.store = Store.objects.create(name='Loja Stats', slug='loja-stats', owner=self.owner, status='active')
        # 2 pagos (100 + 50), 1 pendente (30), 1 falho (não conta nem em pago nem pendente)
        for total, pay in [('100.00', 'paid'), ('50.00', 'paid'), ('30.00', 'pending'), ('20.00', 'failed')]:
            StoreOrder.objects.create(
                store=self.store, customer_name='C', customer_phone='+550000',
                subtotal=Decimal(total), total=Decimal(total), payment_status=pay,
            )
        # Loja vizinha: NÃO pode vazar nos números
        other_owner = User.objects.create_user(username='ow2-stats', email='ow2@t.com', password='x')
        other = Store.objects.create(name='Outra', slug='outra-stats', owner=other_owner, status='active')
        StoreOrder.objects.create(store=other, customer_name='X', customer_phone='+551111',
                                  subtotal=Decimal('999.00'), total=Decimal('999.00'), payment_status='paid')

        self.client.force_authenticate(self.owner)

    def test_payment_status_counts_and_pending_revenue(self):
        resp = self.client.get(f'/api/v1/stores/orders/stats/?store={self.store.slug}')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data
        self.assertEqual(data['by_payment_status']['paid'], 2)
        self.assertEqual(data['by_payment_status']['pending'], 1)
        self.assertEqual(Decimal(str(data['revenue']['total'])), Decimal('150.00'))
        self.assertEqual(Decimal(str(data['revenue']['pending'])), Decimal('30.00'))
        # isolamento: os 999 da outra loja não entram
        self.assertEqual(data['total'], 4)
