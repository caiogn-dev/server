"""
TDD da integração Orders API (mp_orders): payload rico a partir do pedido real.
Sem tocar a API do MP (funções puras + create_order com requests mockado).
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services import mp_orders


class MpOrdersTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o', 'o@x.com', 'x')
        self.store = Store.objects.create(name='Cê Saladas!', slug='ce', owner=self.owner,
                                          status=Store.StoreStatus.ACTIVE)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Maria Silva Souza',
            customer_email='maria@x.com', customer_phone='+55 (63) 99988-7766',
            delivery_address={'zip_code': '77000-000', 'street_name': 'Rua A',
                              'number': '123', 'city': 'Palmas', 'state': 'TO'},
            subtotal=Decimal('100.00'), total=Decimal('100.00'),
        )
        StoreOrderItem.objects.create(order=self.order, product_name='Salada Caesar',
                                      sku='SKU-1', unit_price=Decimal('60.00'), quantity=1)
        StoreOrderItem.objects.create(order=self.order, product_name='Suco',
                                      sku='SKU-2', unit_price=Decimal('40.00'), quantity=2)

    def test_split_name_e_phone(self):
        self.assertEqual(mp_orders.split_name('Maria Silva Souza'), ('Maria', 'Silva Souza'))
        self.assertEqual(mp_orders.phone_parts('+55 (63) 99988-7766'), ('63', '999887766'))

    def test_statement_descriptor_sanitiza(self):
        self.assertEqual(mp_orders.statement_descriptor(self.store), 'CARDAPIDEX')  # sem '!', <=13

    def test_build_items(self):
        items = mp_orders.build_items(self.order)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['title'], 'Salada Caesar')
        self.assertEqual(items[0]['quantity'], 1)
        self.assertEqual(items[0]['unit_price'], '60.00')
        self.assertEqual(items[0]['external_code'], 'SKU-1')
        self.assertEqual(items[0]['category_id'], 'food')

    def test_build_items_external_code_max_30_chars(self):
        """MP Orders API rejeita external_code > 30 chars (400 property_value).
        Item sem SKU cai no product_id (UUID = 36 chars) e derrubava TODO
        pagamento de cartão do site."""
        from apps.stores.models import StoreProduct
        product = StoreProduct.objects.create(
            store=self.store, name='Sem SKU', price=Decimal('10.00'), status='active',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Sem SKU',
            unit_price=Decimal('10.00'), quantity=1,
        )
        items = mp_orders.build_items(self.order)
        for it in items:
            if 'external_code' in it:
                self.assertLessEqual(len(it['external_code']), 30, it)

    def test_build_payer_completo(self):
        payer = mp_orders.build_payer(self.order, 'maria@x.com',
                                      {'identification_type': 'CPF', 'identification_number': '191.191.191-00'})
        self.assertEqual(payer['first_name'], 'Maria')
        self.assertEqual(payer['last_name'], 'Silva Souza')
        self.assertEqual(payer['identification'], {'type': 'CPF', 'number': '19119119100'})
        self.assertEqual(payer['phone'], {'area_code': '63', 'number': '999887766'})
        self.assertEqual(payer['address']['city'], 'Palmas')
        self.assertEqual(payer['address']['state'], 'TO')
        self.assertEqual(payer['address']['zip_code'], '77000000')
        self.assertEqual(payer['address']['street_number'], '123')

    def test_build_order_payload(self):
        p = mp_orders.build_order_payload(self.order, card_token='TKN', payment_method_id='master',
                                          installments=1, payer_email='maria@x.com',
                                          payer_data={'identification_type': 'CPF', 'identification_number': '19119119100'})
        self.assertEqual(p['type'], 'online')
        self.assertEqual(p['total_amount'], '100.00')
        self.assertEqual(p['external_reference'], str(self.order.id))
        pay = p['transactions']['payments'][0]
        self.assertEqual(pay['payment_method']['token'], 'TKN')
        self.assertEqual(pay['payment_method']['statement_descriptor'], 'CARDAPIDEX')
        self.assertEqual(len(p['items']), 2)

    def test_interpret_aprovado(self):
        ok, st, pid, det = mp_orders.interpret(201, {'status': 'processed', 'status_detail': 'accredited',
                                                     'transactions': {'payments': [{'id': 'PAY1', 'status_detail': 'accredited'}]}})
        self.assertTrue(ok); self.assertEqual(st, 'approved'); self.assertEqual(pid, 'PAY1')

    def test_interpret_pendente_e_falha(self):
        ok, st, *_ = mp_orders.interpret(201, {'status': 'action_required', 'transactions': {'payments': [{'id': 'P'}]}})
        self.assertTrue(ok); self.assertEqual(st, 'pending')
        ok2, st2, *_ = mp_orders.interpret(400, {'message': 'invalid'})
        self.assertFalse(ok2); self.assertEqual(st2, 'failed')

    def test_create_order_mockado(self):
        fake = MagicMock(status_code=201)
        fake.json.return_value = {'id': 'ORD1', 'status': 'processed',
                                  'transactions': {'payments': [{'id': 'PAY1'}]}}
        with patch.object(mp_orders.requests, 'post', return_value=fake) as mpost:
            sc, body = mp_orders.create_order('TEST-TOKEN', {'x': 1}, device_id='dev123')
        self.assertEqual(sc, 201)
        self.assertEqual(body['id'], 'ORD1')
        # device id vai no header
        _, kwargs = mpost.call_args
        self.assertEqual(kwargs['headers']['X-meli-session-id'], 'dev123')
        self.assertIn('X-Idempotency-Key', kwargs['headers'])
