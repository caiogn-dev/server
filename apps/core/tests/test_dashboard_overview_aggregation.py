"""Caracterização + performance: DashboardOverviewView dispara ~15 counts/
aggregates sequenciais sobre os MESMOS querysets (messages/orders/agent/
accounts). Este teste trava os VALORES da resposta (para o refactor de
consolidação em .aggregate() não alterar o comportamento) e mede a queda na
contagem de queries.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

URL = '/api/v1/core/dashboard/overview/'


class DashboardOverviewAggregationTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='dash-admin', email='da@t.com', password='x')
        self.account = WhatsAppAccount.objects.create(
            name='acc', phone_number_id='pn-d', waba_id='wa-d',
            phone_number='+5511000333', display_phone_number='+5511000333',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.admin,
            status='active',
        )
        self.store = Store.objects.create(
            owner=self.admin, name='Loja Dash', slug='loja-dash', status=Store.StoreStatus.ACTIVE,
        )
        now = timezone.now()
        # 2 pagos hoje (150) + 1 pendente
        for total, pay, paid in [('100.00', 'paid', now), ('50.00', 'paid', now), ('30.00', 'pending', None)]:
            StoreOrder.objects.create(
                store=self.store, customer_name='C', customer_phone='+55',
                subtotal=Decimal(total), total=Decimal(total), payment_status=pay,
                paid_at=paid, is_active=True,
            )

    def test_valores_da_resposta(self):
        self.client.force_authenticate(self.admin)
        # `?store=` escopa à loja do teste. Sem isso o admin é superusuário e
        # o endpoint agrega TODAS as lojas do banco de teste compartilhado —
        # os contadores vinham contaminados por resíduo de outras suítes.
        resp = self.client.get(URL, {'store': self.store.slug})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data

        self.assertEqual(data['orders']['today'], 3)
        self.assertEqual(float(data['orders']['revenue_today']), 150.0)
        self.assertEqual(data['payments']['pending'], 1)
        self.assertEqual(data['payments']['completed_today'], 2)
        self.assertEqual(data['accounts']['total'], 1)
        self.assertEqual(data['accounts']['active'], 1)
        self.assertEqual(data['accounts']['inactive'], 0)

    def test_query_count_limitado(self):
        self.client.force_authenticate(self.admin)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(URL)
        # Após consolidar os blocos de mesmo queryset em .aggregate(), o total
        # de queries do endpoint deve ficar bem abaixo do padrão antigo (~20+).
        self.assertLessEqual(
            len(ctx.captured_queries), 16,
            f'dashboard fez {len(ctx.captured_queries)} queries (esperado ≤16 após consolidação)',
        )
