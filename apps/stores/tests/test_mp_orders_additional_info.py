"""additional_info (industry data) da Orders API — requisito do quality score do MP.

O checklist de Qualidade da Integração pontua o envio de dados de indústria
(additional_info com chaves ACHATADAS: "payer.registration_date",
"shipment.local_pickup", ...) em toda criação de order. Os dados saem do
histórico real do cliente na loja (por telefone — identidade mais estável no
delivery, já que guest checkout nem sempre tem email/FK de usuário).
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder
from apps.stores.services import mp_orders

User = get_user_model()


class BuildAdditionalInfoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='dono-mp', password='x')
        cls.store = Store.objects.create(name='Loja MP', slug='loja-mp', owner=cls.owner)

    def _order(self, phone='+5563999990000', **kw):
        defaults = dict(
            store=self.store,
            customer_name='Cliente Teste',
            customer_phone=phone,
            subtotal=50,
            total=50,
            status='pending',
        )
        defaults.update(kw)
        return StoreOrder.objects.create(**defaults)

    def test_primeira_compra(self):
        order = self._order()
        info = mp_orders.build_additional_info(order)
        self.assertTrue(info['payer.is_first_purchase_online'])
        self.assertNotIn('payer.last_purchase', info)
        # Sem histórico: registro = criação do próprio pedido (ISO com timezone)
        self.assertIn('T', info['payer.registration_date'])

    def test_cliente_recorrente(self):
        antigo = self._order(payment_status='paid')
        order = self._order()
        info = mp_orders.build_additional_info(order)
        self.assertFalse(info['payer.is_first_purchase_online'])
        self.assertEqual(
            info['payer.registration_date'],
            antigo.created_at.isoformat(timespec='milliseconds'),
        )
        self.assertEqual(
            info['payer.last_purchase'],
            antigo.created_at.isoformat(timespec='milliseconds'),
        )

    def test_pickup_vs_delivery(self):
        pickup = self._order(delivery_method=StoreOrder.DeliveryMethod.PICKUP)
        self.assertTrue(mp_orders.build_additional_info(pickup)['shipment.local_pickup'])
        entrega = self._order(delivery_method=StoreOrder.DeliveryMethod.DELIVERY)
        self.assertFalse(mp_orders.build_additional_info(entrega)['shipment.local_pickup'])

    def test_payload_da_order_inclui_additional_info(self):
        order = self._order()
        payload = mp_orders.build_order_payload(
            order,
            card_token='tok',
            payment_method_id='visa',
            installments=1,
            payer_email='c@x.com',
        )
        self.assertIn('additional_info', payload)
        self.assertIn('payer.registration_date', payload['additional_info'])
