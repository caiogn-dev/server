"""Regressão de segurança: is_staff vazava métricas cross-tenant no dashboard.

`_accessible_accounts` e `_accessible_stores` retornavam TODAS as contas/lojas
quando `user.is_staff` — então qualquer conta com acesso ao /admin via as
métricas (pedidos, RECEITA, contas) de TODOS os tenants em
/core/dashboard/overview/. Mesma família do fix de intent_views: só
is_superuser tem acesso cross-tenant.

Cenários:
  1. Atacante is_staff NÃO vê contas nem receita de outro tenant.
  2. superuser continua vendo tudo (guarda de não-regressão).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

URL = '/api/v1/core/dashboard/overview/'


class DashboardIsStaffIDORTest(APITestCase):
    def setUp(self):
        self.victim = User.objects.create_user(username='dv', email='dv@t.com', password='x')
        self.victim_acc = WhatsAppAccount.objects.create(
            name='v', phone_number_id='pn-dv', waba_id='wa-dv',
            phone_number='+5511000444', display_phone_number='+5511000444',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.victim,
            status='active',
        )
        self.victim_store = Store.objects.create(
            owner=self.victim, name='Loja Vitima', slug='dash-vitima', status=Store.StoreStatus.ACTIVE,
        )
        StoreOrder.objects.create(
            store=self.victim_store, customer_name='C', customer_phone='+55',
            subtotal=Decimal('500.00'), total=Decimal('500.00'), payment_status='paid',
            paid_at=timezone.now(), is_active=True,
        )
        self.attacker = User.objects.create_user(
            username='da', email='da@t.com', password='x', is_staff=True,
        )
        self.superuser = User.objects.create_superuser(username='ds', email='ds@t.com', password='x')

    def test_staff_nao_ve_metricas_de_outro_tenant(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['accounts']['total'], 0)
        self.assertEqual(resp.data['orders']['today'], 0)
        self.assertEqual(float(resp.data['orders']['revenue_today']), 0.0)
        # Exclui 'timestamp' antes do assertNotIn: o ISO datetime pode
        # conter a substring '500' por coincidência (ex.: microssegundos
        # terminando em ...500...), o que produzia falso-positivo flaky
        # sem relação nenhuma com vazamento de dados cross-tenant.
        leak_check_data = {k: v for k, v in resp.data.items() if k != 'timestamp'}
        self.assertNotIn('500', str(leak_check_data))

    def test_superuser_ve_tudo(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['accounts']['total'], 1)
        self.assertEqual(float(resp.data['orders']['revenue_today']), 500.0)
