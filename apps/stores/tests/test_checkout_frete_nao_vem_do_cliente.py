"""O frete do pedido é do servidor — nunca o número que o navegador mandou.

`StorefrontCheckoutViewSet._extract_delivery_data` copiava
`request.data['delivery_fee']` para `delivery_data['fee']` (986b7cc7, 30/05:
"aceitar delivery_fee pré-computado"). E `CheckoutService` trata `fee` não-nulo
como taxa pronta (WhatsApp override): pula o cálculo inteiro. Resultado: o
endpoint PÚBLICO de checkout aceitava `"delivery_fee": 0` e o pedido nascia
com frete zero, a qualquer distância.

Nenhum cliente legítimo manda esse campo (cardapidex-web useCheckoutForm envia
`lat`/`lng` + `delivery_distance_km`; o app Flutter, nada). Quem precisa de taxa
pronta tem porta própria e autenticada: `trusted_delivery_fee` (PDV/painel) e o
override do bot do WhatsApp, que chamam o serviço direto.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCategory, StoreOrder, StoreProduct

User = get_user_model()

ROTA_3KM = {'distance_meters': 3000, 'duration_seconds': 600}


@patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value=None)
@patch('apps.stores.services.geo.service.GeoService.geocode', return_value=None)
@patch('apps.stores.services.geo.google_provider.GoogleMapsProvider.route', return_value=ROTA_3KM)
class FreteNaoVemDoClienteTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-frete', password='x')
        self.store = Store.objects.create(
            owner=dono, name='Loja Frete', slug='loja-frete',
            status=Store.StoreStatus.ACTIVE,
            default_delivery_fee=Decimal('8.00'),
            latitude=Decimal('-10.1852683'), longitude=Decimal('-48.3036368'),
            city='Palmas', state='TO',
        )
        cat = StoreCategory.objects.create(store=self.store, name='C', slug='c', is_active=True)
        self.produto = StoreProduct.objects.create(
            store=self.store, category=cat, name='Salada', slug='salada',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.client = APIClient()
        self.url = f'/api/v1/stores/{self.store.slug}'

    def _checkout(self, **extra):
        r = self.client.post(f'{self.url}/cart/add/', {'product_id': str(self.produto.id), 'quantity': 1}, format='json')
        self.assertIn(r.status_code, (200, 201), r.data)
        corpo = {
            'customer_name': 'Ana', 'customer_phone': '63999990000', 'customer_email': 'ana@example.com',
            'payment_method': 'cash', 'delivery_method': 'delivery',
            'delivery_address': {'street': 'Quadra 104 Norte', 'number': '10', 'city': 'Palmas', 'state': 'TO'},
            'lat': -10.2000, 'lng': -48.3300,
        }
        corpo.update(extra)
        return self.client.post(f'{self.url}/checkout/', corpo, format='json')

    def _pedido(self):
        return StoreOrder.objects.get(store=self.store)

    def test_sem_delivery_fee_o_servidor_calcula(self, *_):
        r = self._checkout()
        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertEqual(self._pedido().delivery_fee, Decimal('8.00'))

    def test_delivery_fee_zero_do_cliente_e_ignorado(self, *_):
        r = self._checkout(delivery_fee=0)
        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertEqual(self._pedido().delivery_fee, Decimal('8.00'))

    def test_delivery_fee_inflado_do_cliente_e_ignorado(self, *_):
        r = self._checkout(delivery_fee='99.90')
        self.assertIn(r.status_code, (200, 201), r.data)
        self.assertEqual(self._pedido().delivery_fee, Decimal('8.00'))
