"""Regressão de segurança (IDOR): a action stats do StoreOrderViewSet vazava
receita/contagem cross-tenant.

stats consultava `StoreOrder.objects.all()` e só aplicava `filter_by_store`
quando o param `store` era passado — ignorando o escopo do usuário. Assim,
qualquer autenticado:
  (a) passava `?store=<loja-alheia>` e lia a receita da concorrente; ou
  (b) NÃO passava `store` e recebia os números AGREGADOS de TODAS as lojas.

Cenários:
  1. IDOR direto: owner_a NÃO vê os números da loja de owner_b via ?store=.
  2. IDOR agregado: sem ?store=, owner_a só vê os próprios pedidos (não o global).
  3. Regressão: owner_a continua vendo corretamente a própria loja.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()

STATS_URL = '/api/v1/stores/orders/stats/'


class OrderStatsIDORTest(APITestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(username='st-a', email='st-a@t.com', password='x')
        self.store_a = Store.objects.create(name='Loja A', slug='st-loja-a', owner=self.owner_a, status='active')
        StoreOrder.objects.create(store=self.store_a, customer_name='C', customer_phone='+55A',
                                  subtotal=Decimal('10.00'), total=Decimal('10.00'), payment_status='paid')

        self.owner_b = User.objects.create_user(username='st-b', email='st-b@t.com', password='x')
        self.store_b = Store.objects.create(name='Loja B', slug='st-loja-b', owner=self.owner_b, status='active')
        # Receita secreta da concorrente — NÃO pode vazar em hipótese alguma.
        StoreOrder.objects.create(store=self.store_b, customer_name='X', customer_phone='+55B',
                                  subtotal=Decimal('999.00'), total=Decimal('999.00'), payment_status='paid')

    def test_owner_a_nao_ve_stats_da_loja_b_via_param(self):
        """Passar ?store=<loja-B> não deve vazar os números da loja B."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.get(f'{STATS_URL}?store={self.store_b.slug}')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['total'], 0, resp.data)
        self.assertEqual(Decimal(str(resp.data['revenue']['total'])), Decimal('0'))
        self.assertNotIn('999', str(resp.data))

    def test_owner_a_sem_param_nao_agrega_todas_as_lojas(self):
        """Sem ?store=, owner_a só vê os próprios pedidos (não o total global)."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.get(STATS_URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['total'], 1, resp.data)
        self.assertEqual(Decimal(str(resp.data['revenue']['total'])), Decimal('10.00'))
        self.assertNotIn('999', str(resp.data))

    def test_owner_a_ve_a_propria_loja(self):
        """Regressão: owner_a continua enxergando a própria loja normalmente."""
        self.client.force_authenticate(self.owner_a)
        resp = self.client.get(f'{STATS_URL}?store={self.store_a.slug}')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(Decimal(str(resp.data['revenue']['total'])), Decimal('10.00'))
