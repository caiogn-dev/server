"""Correções de campos que zeravam painéis no pastita-dash.

1. Filtro de pedidos por `customer` (histórico do cliente no drawer) casava telefone
   por igualdade exata — qualquer diferença de formato (+55, espaços, parênteses)
   zerava o histórico. Agora compara só dígitos pelo sufixo nacional.
2. Stats de cupons não devolvia a chave `inactive` que o card "Inativos" lê.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.models.coupon import StoreCoupon

User = get_user_model()


class OrderCustomerPhoneFilterTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-phone', email='ow-phone@t.com', password='x')
        self.store = Store.objects.create(name='Loja Phone', slug='loja-phone', owner=self.owner, status='active')
        # Mesmo cliente, customer_phone gravado COM DDI e formatação no checkout
        for i in range(3):
            StoreOrder.objects.create(
                store=self.store, customer_name='Cliente A',
                customer_phone='+55 (63) 99988-7766',
                subtotal=Decimal('10.00'), total=Decimal('10.00'), payment_status='paid',
            )
        # Outro cliente: não pode vazar no histórico
        StoreOrder.objects.create(
            store=self.store, customer_name='Cliente B', customer_phone='63988776655',
            subtotal=Decimal('99.00'), total=Decimal('99.00'), payment_status='paid',
        )
        self.client.force_authenticate(self.owner)

    def test_history_matches_despite_phone_format(self):
        # Cadastro guarda só dígitos sem DDI — formato diferente do checkout
        resp = self.client.get(f'/api/v1/stores/orders/?store={self.store.slug}&customer=63999887766')
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 3)
        for o in results:
            self.assertEqual(o['customer_name'], 'Cliente A')

    def test_other_customer_not_leaked(self):
        resp = self.client.get(f'/api/v1/stores/orders/?store={self.store.slug}&customer=63988776655')
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['customer_name'], 'Cliente B')


class CouponStatsInactiveTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-coup', email='ow-coup@t.com', password='x')
        self.store = Store.objects.create(name='Loja Coup', slug='loja-coup', owner=self.owner, status='active')
        now = timezone.now()
        # 1 ativo, 2 inativos
        StoreCoupon.objects.create(
            store=self.store, code='ATIVO', discount_type='percentage', discount_value=Decimal('10'),
            is_active=True, valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=30),
        )
        for code in ('OFF1', 'OFF2'):
            StoreCoupon.objects.create(
                store=self.store, code=code, discount_type='percentage', discount_value=Decimal('10'),
                is_active=False, valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=30),
            )
        self.client.force_authenticate(self.owner)

    def test_inactive_key_present_and_correct(self):
        resp = self.client.get(f'/api/v1/stores/coupons/stats/?store={self.store.slug}')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn('inactive', resp.data)
        self.assertEqual(resp.data['inactive'], 2)
        self.assertEqual(resp.data['active'], 1)
        self.assertEqual(resp.data['total'], 3)


class MarketingWhatsAppStatsTest(APITestCase):
    """O painel de Marketing zerava o card 'WhatsApp Enviados' (total_sent/read_rate
    hardcoded em 0 no front por falta do bloco 'whatsapp' no endpoint /marketing/stats/).
    O backend agora agrega as campanhas WhatsApp da loja via StoreIntegration→account.
    """

    def setUp(self):
        from apps.stores.models import StoreIntegration
        from apps.whatsapp.models.account import WhatsAppAccount
        from apps.campaigns.models import Campaign

        self.owner = User.objects.create_user(username='ow-mkt', email='ow-mkt@t.com', password='x')
        self.store = Store.objects.create(name='Loja Mkt', slug='loja-mkt', owner=self.owner, status='active')
        StoreIntegration.objects.create(store=self.store, phone_number_id='PN123', waba_id='WABA123')
        account = WhatsAppAccount.objects.create(
            name='Conta', phone_number_id='PN123', waba_id='WABA123',
            phone_number='5563999999999', access_token_encrypted='x', owner=self.owner,
        )
        Campaign.objects.create(
            account=account, name='Promo 1', messages_sent=100,
            messages_delivered=80, messages_read=40,
        )
        Campaign.objects.create(
            account=account, name='Promo 2', messages_sent=50,
            messages_delivered=50, messages_read=10,
        )
        self.client.force_authenticate(self.owner)

    def test_whatsapp_block_aggregates_campaigns(self):
        resp = self.client.get(f'/api/v1/marketing/stats/?store={self.store.id}')
        self.assertEqual(resp.status_code, 200, resp.content)
        wa = resp.data.get('whatsapp')
        self.assertIsNotNone(wa, 'bloco whatsapp ausente do /marketing/stats/')
        self.assertEqual(wa['total_campaigns'], 2)
        self.assertEqual(wa['total_sent'], 150)
        self.assertEqual(wa['total_delivered'], 130)
        self.assertEqual(wa['total_read'], 50)
        # read_rate = read/delivered = 50/130 ≈ 38.46
        self.assertGreater(wa['read_rate'], 0)
