"""
Testes para WhatsAppOrderService.

Cobertura:
1. _build_delivery_address — mapeamento de componentes HERE Maps para chaves padrão do frontend
2. create_order_from_cart — criação de pedido, decremento de estoque, taxa de entrega
3. create_order_from_cart — tratamento de produto inválido, itens sem produto, erro geral

Executar:
    python manage.py test tests.test_whatsapp_order_service --keepdb -v 2
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreProduct, StoreOrder, StoreOrderItem

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass',
    )


def _make_store(owner, slug='wa-order-test'):
    return Store.objects.create(
        owner=owner,
        name='WA Order Test Store',
        slug=slug,
        is_active=True,
        status='active',
        default_delivery_fee=Decimal('8.00'),
    )


def _make_product(store, name='Produto', price=Decimal('20.00'),
                  track_stock=False, stock_quantity=0):
    return StoreProduct.objects.create(
        store=store,
        name=name,
        price=price,
        status=StoreProduct.ProductStatus.ACTIVE,
        track_stock=track_stock,
        stock_quantity=stock_quantity,
    )


# Caminhos de patch para dependências externas do serviço
_PATCH_PAYMENT   = 'apps.whatsapp.services.order_service.CheckoutService.create_payment'
_PATCH_BROADCAST = 'apps.whatsapp.services.order_service.broadcast_order_event'


# ─── Testes: _build_delivery_address ─────────────────────────────────────────

class BuildDeliveryAddressTest(TestCase):
    """
    Garante que _build_delivery_address mapeia corretamente os campos HERE Maps
    para o formato esperado pelo frontend (street, number, neighborhood, etc.)
    e preserva raw_address como fallback.
    """

    def setUp(self):
        from apps.whatsapp.services.order_service import WhatsAppOrderService
        owner = _make_user('bda_owner')
        store = _make_store(owner, 'bda-store')
        self.svc = WhatsAppOrderService(store=store, phone_number='+5563999990000')

    def test_empty_args_returns_empty_dict(self):
        result = self.svc._build_delivery_address('', None)
        self.assertEqual(result, {})

    def test_raw_address_without_components(self):
        result = self.svc._build_delivery_address('Rua A, 10', None)
        self.assertEqual(result['raw_address'], 'Rua A, 10')
        self.assertNotIn('street', result)
        self.assertNotIn('city', result)

    def test_geocode_components_mapped_correctly(self):
        """
        geocode() retorna keys HERE: houseNumber, district, stateCode, postalCode.
        Devem ser mapeados para: number, neighborhood, state, zip_code.
        """
        addr_info = {
            'lat': -10.18, 'lng': -48.33,
            'distance_km': 4.2, 'duration_minutes': 15,
            'address_components': {
                'street': 'Rua das Flores',
                'houseNumber': '42',
                'district': 'Centro',
                'city': 'Palmas',
                'stateCode': 'TO',
                'postalCode': '77000-000',
            },
        }
        result = self.svc._build_delivery_address('Rua das Flores, 42', addr_info)
        self.assertEqual(result['street'], 'Rua das Flores')
        self.assertEqual(result['number'], '42')
        self.assertEqual(result['neighborhood'], 'Centro')
        self.assertEqual(result['city'], 'Palmas')
        self.assertEqual(result['state'], 'TO')
        self.assertEqual(result['zip_code'], '77000-000')
        self.assertEqual(result['raw_address'], 'Rua das Flores, 42')

    def test_reverse_geocode_components_mapped_correctly(self):
        """
        reverse_geocode() retorna keys normalizadas: house_number, state_code, zip_code.
        Devem ser mapeados para os mesmos campos padrão.
        """
        addr_info = {
            'lat': -10.20, 'lng': -48.35,
            'address_components': {
                'street': 'Alameda 1',
                'house_number': '5',
                'neighborhood': 'Plano Diretor Sul',
                'city': 'Palmas',
                'state_code': 'TO',
                'zip_code': '77023-040',
            },
        }
        result = self.svc._build_delivery_address('Alameda 1, 5', addr_info)
        self.assertEqual(result['number'], '5')
        self.assertEqual(result['neighborhood'], 'Plano Diretor Sul')
        self.assertEqual(result['state'], 'TO')
        self.assertEqual(result['zip_code'], '77023-040')

    def test_partial_components_only_set_fields_present(self):
        """Campos ausentes nos componentes não aparecem no resultado."""
        addr_info = {
            'address_components': {
                'city': 'Palmas',
                'stateCode': 'TO',
            },
        }
        result = self.svc._build_delivery_address('Palmas', addr_info)
        self.assertEqual(result['city'], 'Palmas')
        self.assertEqual(result['state'], 'TO')
        self.assertNotIn('street', result)
        self.assertNotIn('number', result)

    def test_geo_coordinates_always_preserved(self):
        addr_info = {
            'lat': -10.18, 'lng': -48.33,
            'distance_km': 3.5, 'duration_minutes': 12,
        }
        result = self.svc._build_delivery_address('Qualquer', addr_info)
        self.assertEqual(result['lat'], -10.18)
        self.assertEqual(result['lng'], -48.33)
        self.assertEqual(result['distance_km'], 3.5)
        self.assertEqual(result['duration_minutes'], 12)


# ─── Testes: create_order_from_cart ──────────────────────────────────────────

class CreateOrderFromCartTest(TestCase):
    """
    Testa a criação de pedidos via WhatsApp.
    Dependências externas (Mercado Pago, Redis, CompanyProfile) são mockadas.
    """

    def setUp(self):
        self.owner = _make_user('wa_cart_owner')
        self.store = _make_store(self.owner, 'wa-cart-store')
        self.product = _make_product(self.store, 'Pizza', Decimal('25.00'))
        self.items = [{'product_id': str(self.product.id), 'quantity': 2}]

    def _call(self, items=None, delivery_method='pickup', payment_method='cash',
              delivery_fee_override=None, delivery_address='', addr_info=None,
              customer_notes=''):
        """Executa create_order_from_cart com mocks para dependências externas."""
        from apps.whatsapp.services.order_service import WhatsAppOrderService
        svc = WhatsAppOrderService(
            store=self.store,
            phone_number='+5563999990001',
            customer_name='João',
        )
        with patch(_PATCH_PAYMENT, return_value={'success': True}), \
             patch(_PATCH_BROADCAST), \
             patch.object(svc, '_update_session'):
            return svc.create_order_from_cart(
                items=items if items is not None else self.items,
                delivery_method=delivery_method,
                payment_method=payment_method,
                delivery_fee_override=delivery_fee_override,
                delivery_address=delivery_address,
                addr_info=addr_info,
                customer_notes=customer_notes,
            )

    # ── criação básica ──

    def test_pickup_creates_order_with_zero_delivery_fee(self):
        result = self._call(delivery_method='pickup')
        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(order_number=result['order_number'])
        self.assertEqual(order.delivery_method, 'pickup')
        self.assertEqual(order.delivery_fee, Decimal('0'))
        self.assertEqual(order.total, Decimal('50.00'))  # 2 × 25.00

    def test_order_items_created_with_correct_quantity(self):
        result = self._call()
        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(order_number=result['order_number'])
        items = StoreOrderItem.objects.filter(order=order)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().quantity, 2)
        self.assertEqual(items.first().unit_price, Decimal('25.00'))

    def test_delivery_fee_override_applied(self):
        result = self._call(
            delivery_method='delivery',
            delivery_fee_override=12.50,
            delivery_address='Rua A, 10',
        )
        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(order_number=result['order_number'])
        self.assertEqual(order.delivery_fee, Decimal('12.50'))
        self.assertEqual(order.total, Decimal('62.50'))  # 50.00 + 12.50

    def test_metadata_marks_source_as_whatsapp(self):
        result = self._call()
        order = StoreOrder.objects.get(order_number=result['order_number'])
        self.assertEqual(order.metadata.get('source'), 'whatsapp')
        self.assertEqual(order.metadata.get('phone_number'), '+5563999990001')

    # ── estoque ──

    def test_stock_decremented_when_track_stock_true(self):
        product = _make_product(self.store, 'Monitorado', Decimal('30.00'),
                                track_stock=True, stock_quantity=10)
        result = self._call(items=[{'product_id': str(product.id), 'quantity': 3}])
        self.assertTrue(result['success'])
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 7)

    def test_stock_not_decremented_when_track_stock_false(self):
        product = _make_product(self.store, 'Sem controle', Decimal('30.00'),
                                track_stock=False, stock_quantity=0)
        result = self._call(items=[{'product_id': str(product.id), 'quantity': 5}])
        self.assertTrue(result['success'])
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 0)

    # ── tratamento de erros ──

    def test_invalid_product_id_skipped(self):
        invalid_uuid = '00000000-0000-0000-0000-000000000000'
        items = [
            {'product_id': str(self.product.id), 'quantity': 1},
            {'product_id': invalid_uuid, 'quantity': 1},
        ]
        result = self._call(items=items)
        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(order_number=result['order_number'])
        self.assertEqual(StoreOrderItem.objects.filter(order=order).count(), 1)

    def test_all_invalid_products_returns_error(self):
        result = self._call(items=[{'product_id': '00000000-0000-0000-0000-000000000000', 'quantity': 1}])
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())
