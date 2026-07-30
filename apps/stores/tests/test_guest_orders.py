"""Endpoint /customer/guest-orders/ — histórico por telefone SEM login.

Decisão de produto: o storefront não tem login obrigatório (identidade guest
por telefone, useGuestInfo 90d — mesmo elo da fidelidade guest-status).
"Meus pedidos" e "Pedir novamente" precisam funcionar só com o número.

Também regressão do reorder: os itens devem vir COMPLETOS (sem corte em 3)
e com o id da variante (`variant`), senão o resolveReorderItems do web pula
produto com variante obrigatória.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient

from apps.stores.models import Store, StoreOrder, StoreOrderItem

User = get_user_model()

PHONE = '63999547790'


class GuestOrdersTests(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username='owner-go', email='og@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja GO', slug='loja-go', owner=owner, status='active',
        )
        self.client = APIClient()

    def _url(self, slug=None):
        return f'/api/v1/stores/{slug or self.store.slug}/customer/guest-orders/'

    def _order(self, phone=PHONE, **kw):
        defaults = dict(store=self.store, subtotal=30, total=30,
                        status='delivered', customer_phone=phone)
        defaults.update(kw)
        return StoreOrder.objects.create(**defaults)

    def test_sem_telefone_devolve_lista_vazia(self):
        resp = self.client.post(self._url(), {'phone': ''}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['results'], [])

    def test_encontra_pedidos_pelo_telefone_local(self):
        self._order()
        resp = self.client.post(self._url(), {'phone': PHONE}, format='json')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertIn('access_token', results[0])
        self.assertIn('order_number', results[0])

    def test_casa_variantes_com_e_sem_55(self):
        # Pedido gravado com 55 na frente; consulta com número local formatado
        self._order(phone=f'55{PHONE}')
        resp = self.client.post(
            self._url(), {'phone': '(63) 99954-7790'}, format='json')
        self.assertEqual(len(resp.json()['results']), 1)

    def test_nao_vaza_pedido_de_outro_telefone(self):
        self._order(phone='63911112222')
        resp = self.client.post(self._url(), {'phone': PHONE}, format='json')
        self.assertEqual(resp.json()['results'], [])

    def test_nao_vaza_pedido_de_outra_loja(self):
        other_owner = User.objects.create_user(username='owner-go2', password='x')
        other = Store.objects.create(
            name='Outra', slug='loja-go2', owner=other_owner, status='active')
        StoreOrder.objects.create(
            store=other, subtotal=10, total=10, status='delivered',
            customer_phone=PHONE)
        resp = self.client.post(self._url(), {'phone': PHONE}, format='json')
        self.assertEqual(resp.json()['results'], [])

    def test_itens_completos_com_variant(self):
        order = self._order()
        for i in range(5):
            StoreOrderItem.objects.create(
                order=order, product_name=f'Salada {i}',
                unit_price=10, quantity=1, subtotal=10,
            )
        resp = self.client.post(self._url(), {'phone': PHONE}, format='json')
        result = resp.json()['results'][0]
        self.assertEqual(len(result['items']), 5)  # sem corte em 3
        self.assertIn('variant', result['items'][0])
        self.assertIn('product', result['items'][0])
