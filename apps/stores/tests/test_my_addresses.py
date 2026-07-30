"""Endpoint /customer/my-addresses/ — regressão do FieldError e seed por pedidos.

Bug real: o viewset lia `request.user.unified_user` (related_name correto é
`unified_profile`) e filtrava `UnifiedUser.objects.filter(user=...)` (campo é
`django_user`) → 500 em toda listagem; o perfil mostrava "nenhum endereço".
Além do fix, a lista semeia endereços estruturados dos pedidos recentes do
usuário quando está vazia.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient

from apps.core.models import UserProfile
from apps.stores.models import Store, StoreOrder
from apps.users.models import UserAddress

User = get_user_model()

PHONE = '63999547790'


class MyAddressesTests(APITestCase):
    def setUp(self):
        owner = User.objects.create_user(username='owner-addr', email='oa@t.com', password='x')
        self.store = Store.objects.create(
            name='Loja Addr', slug='loja-addr', owner=owner, status='active',
        )
        self.user = User.objects.create_user(username=f'cliente_55{PHONE}', password='x')
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.phone = f'55{PHONE}'
        profile.save(update_fields=['phone'])
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return f'/api/v1/stores/{self.store.slug}/customer/my-addresses/'

    def test_lista_vazia_nao_estoura(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)

    def test_semeia_endereco_do_pedido_recente_do_usuario(self):
        StoreOrder.objects.create(
            store=self.store, customer=self.user, subtotal=30, total=30,
            status='delivered', customer_phone=PHONE,
            delivery_address={
                'street': 'Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins',
                'city': 'Palmas', 'state': 'TO', 'zip_code': '77020170',
            },
        )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        results = resp.json()
        rows = results.get('results', results)
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn('112 Sul', rows[0]['street'])

    def test_semeia_por_telefone_quando_pedido_esta_em_outro_usuario(self):
        other = User.objects.create_user(username='zz-outro-user', password='x')
        StoreOrder.objects.create(
            store=self.store, customer=other, subtotal=30, total=30,
            status='delivered', customer_phone=PHONE,
            delivery_address={
                'street': 'Q. 112 Sul, Rua Sr 01, 2', 'city': 'Palmas',
                'state': 'TO', 'zip_code': '77020170',
            },
        )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        rows = rows.get('results', rows)
        self.assertGreaterEqual(len(rows), 1)

    def test_nao_duplica_seed_em_listagens_repetidas(self):
        StoreOrder.objects.create(
            store=self.store, customer=self.user, subtotal=30, total=30,
            status='delivered', customer_phone=PHONE,
            delivery_address={'street': 'Rua A', 'number': '10', 'city': 'Palmas', 'state': 'TO'},
        )
        self.client.get(self._url())
        self.client.get(self._url())
        self.assertEqual(
            UserAddress.objects.filter(tenant=self.store).count(), 1,
        )
