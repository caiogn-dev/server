"""Regressão N+1: a lista de clientes não pode escalar queries com o nº de clientes.

Antes: StoreCustomerSerializer.get_default_address chamava address_list.filter(...)
por linha → 1 query por cliente (N+1 em store_customer_addresses). Este teste prova
O(1) com dois pontos de dados (5 e 15 clientes) — a contagem de queries não muda.
"""
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.customer import StoreCustomer, StoreCustomerAddress

User = get_user_model()


class CustomersListNoN1Test(APITestCase):
    def _make_store_with_customers(self, slug, n):
        owner = User.objects.create_user(username=f'own-{slug}', email=f'own-{slug}@t.com', password='x')
        store = Store.objects.create(name=f'Loja {slug}', slug=slug, owner=owner, status='active')
        for i in range(n):
            u = User.objects.create_user(username=f'u-{slug}-{i}', email=f'u-{slug}-{i}@t.com', password='x')
            c = StoreCustomer.objects.create(store=store, user=u, phone=f'+5500{i:05d}')
            # 2 endereços por cliente: o N+1 dispararia uma query por cliente aqui.
            StoreCustomerAddress.objects.create(customer=c, street='Rua A', number='1', is_default=False)
            StoreCustomerAddress.objects.create(customer=c, street='Rua B', number='2', is_default=True)
        return owner, store

    def _count_list_queries(self, owner, store):
        self.client.force_authenticate(owner)
        url = f'/api/v1/stores/customers/?store={store.slug}&page_size=100'
        self.client.get(url)  # warmup (content types, etc.)
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx.captured_queries)

    def test_query_count_is_constant_regardless_of_customer_count(self):
        o5, s5 = self._make_store_with_customers('n1-small', 5)
        o15, s15 = self._make_store_with_customers('n1-big', 15)
        q5 = self._count_list_queries(o5, s5)
        q15 = self._count_list_queries(o15, s15)
        # O(1): triplicar os clientes NÃO pode aumentar as queries.
        self.assertEqual(
            q5, q15,
            f'N+1 detectado: 5 clientes={q5} queries, 15 clientes={q15} queries '
            f'(deveria ser constante).'
        )
