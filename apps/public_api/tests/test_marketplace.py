"""GET /api/v1/public/marketplace/ — vitrine de lojas do app Cardapidex."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store, StoreCategory, StoreProduct

URL = '/api/v1/public/marketplace/'


def make_store(owner, slug, **kw):
    defaults = dict(
        name=slug.title(), slug=slug, status='active',
        whatsapp_number='63999990000', address='Rua X, 1',
        city='Palmas', state='TO', plan='free',
        logo_url='https://cdn.exemplo.com/logo.png',
    )
    defaults.update(kw)
    return Store.objects.create(owner=owner, **defaults)


def add_product(store, n=1):
    cat = StoreCategory.objects.create(store=store, name='Cat', slug=f'cat-{store.slug}')
    for i in range(n):
        StoreProduct.objects.create(
            store=store, category=cat, name=f'P{i}', slug=f'p{i}-{store.slug}',
            price=Decimal('10.00'), is_active=True, sku=f'{store.slug}-{i}',
            track_stock=False,
        )


class MarketplaceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='mkt', email='mkt@example.com', password='x')

    def _slugs(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        return [s['slug'] for s in resp.json()['lojas']]

    def test_publico_sem_login(self):
        add_product(make_store(self.owner, 'boa'))
        self.assertEqual(self._slugs(), ['boa'])

    def test_so_entra_loja_pronta(self):
        add_product(make_store(self.owner, 'boa'))
        add_product(make_store(self.owner, 'sem-logo', logo_url=''))
        add_product(make_store(self.owner, 'sem-cidade', city=''))
        add_product(make_store(self.owner, 'inativa', status='inactive'))
        make_store(self.owner, 'sem-produto')
        add_product(make_store(self.owner, 'escondida',
                               metadata={'fora_do_marketplace': True}))
        self.assertEqual(self._slugs(), ['boa'])

    def test_campos_do_card(self):
        loja = make_store(
            self.owner, 'ce', name='Cê Saladas', tagline='Salada boa',
            default_delivery_fee=Decimal('8.00'), min_order_value=Decimal('20.00'),
            prazo_entrega_min=40, prazo_entrega_max=60, primary_color='#1B5E20',
        )
        add_product(loja, 3)
        item = self.client.get(URL).json()['lojas'][0]
        self.assertEqual(item['nome'], 'Cê Saladas')
        self.assertEqual(item['descricao'], 'Salada boa')
        self.assertEqual(item['cidade'], 'Palmas')
        self.assertEqual(item['frete'], '8.00')
        self.assertEqual(item['pedido_minimo'], '20.00')
        self.assertEqual(item['prazo_min'], 40)
        self.assertEqual(item['prazo_max'], 60)
        self.assertEqual(item['cor'], '#1B5E20')
        self.assertEqual(item['total_produtos'], 3)
        self.assertIn('aberta', item)
        self.assertIn('nota', item)
        self.assertTrue(item['logo_url'].startswith('https://'))

    def test_aberta_primeiro(self):
        fechada = make_store(self.owner, 'a-fechada', metadata={'pausas': [{
            'inicio': '2000-01-01T00:00:00-03:00', 'fim': '2999-01-01T00:00:00-03:00'}]})
        add_product(fechada)
        add_product(make_store(self.owner, 'z-aberta'))
        lojas = self.client.get(URL).json()['lojas']
        self.assertEqual([(l['slug'], l['aberta']) for l in lojas],
                         [('z-aberta', True), ('a-fechada', False)])
