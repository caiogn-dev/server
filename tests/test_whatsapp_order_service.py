"""
Testes para WhatsAppOrderService.

Cobertura:
1. _build_delivery_address — mapeamento de componentes de geocode para chaves padrão do frontend
2. create_order_from_cart — criação de pedido, decremento de estoque, taxa de entrega
3. create_order_from_cart — tratamento de produto inválido, itens sem produto, erro geral

Executar:
    python manage.py test tests.test_whatsapp_order_service --keepdb -v 2
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreProduct,
    StoreOrder,
    StoreOrderItem,
)
from apps.stores.services.checkout_service import CheckoutService

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
        slug=f"{name.lower().replace(' ', '-')}-{StoreProduct.objects.count()}",
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
    Garante que _build_delivery_address mapeia corretamente os campos do provider de geocode
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
        geocode() pode retornar keys legadas: houseNumber, district, stateCode, postalCode.
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

    def test_out_of_stock_returns_error_with_estoque_keyword(self):
        product = _make_product(self.store, 'Esgotado', Decimal('30.00'),
                                track_stock=True, stock_quantity=0)
        result = self._call(items=[{'product_id': str(product.id), 'quantity': 1}])
        self.assertFalse(result['success'])
        error = result.get('error', '')
        self.assertTrue(
            'estoque' in error.lower() or 'Erros de estoque' in error,
            f"Expected stock error message, got: {error!r}",
        )
        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())


class WhatsAppCheckoutEquivalenceTest(TestCase):
    """
    Guards the minimum order-shape equivalence required before moving WhatsApp
    order creation behind CheckoutService.
    """

    def setUp(self):
        self.owner = _make_user('wa_checkout_equiv_owner')
        self.customer = _make_user('wa_checkout_equiv_customer')
        self.store = _make_store(self.owner, 'wa-checkout-equiv-store')
        self.product = _make_product(self.store, 'Salada', Decimal('31.50'))

    def _checkout_order(self, delivery_method='pickup'):
        cart = StoreCart.objects.create(store=self.store, user=self.customer)
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=2)
        delivery_data = {'method': delivery_method}
        if delivery_method == 'delivery':
            delivery_data['address'] = {'raw_address': 'Rua A, 10'}

        with patch('apps.stores.services.checkout_service.trigger_order_email_automation'):
            return CheckoutService.create_order(
                cart=cart,
                customer_data={
                    'name': 'Jesse',
                    'email': 'jesse@example.com',
                    'phone': '+556392732632',
                },
                delivery_data=delivery_data,
                notes='Contrato equivalencia',
            )

    def _whatsapp_order(self, delivery_method='pickup', payment_method='cash'):
        from apps.whatsapp.services.order_service import WhatsAppOrderService

        svc = WhatsAppOrderService(
            store=self.store,
            phone_number='+556392732632',
            customer_name='Jesse',
        )
        with patch(_PATCH_PAYMENT, return_value={'success': True}), \
             patch(_PATCH_BROADCAST), \
             patch.object(svc, '_update_session'):
            result = svc.create_order_from_cart(
                items=[{'product_id': str(self.product.id), 'quantity': 2}],
                delivery_method=delivery_method,
                payment_method=payment_method,
                delivery_address='Rua A, 10' if delivery_method == 'delivery' else '',
                customer_notes='Contrato equivalencia',
            )

        self.assertTrue(result['success'], result)
        return StoreOrder.objects.get(order_number=result['order_number'])

    def _order_snapshot(self, order):
        item = order.items.get()
        return {
            'subtotal': order.subtotal,
            'delivery_fee': order.delivery_fee,
            'total': order.total,
            'delivery_method': order.delivery_method,
            'item_name': item.product_name,
            'item_quantity': item.quantity,
            'item_unit_price': item.unit_price,
            'item_subtotal': item.subtotal,
        }

    def test_pickup_order_shape_matches_checkout_service(self):
        checkout_order = self._checkout_order(delivery_method='pickup')
        whatsapp_order = self._whatsapp_order(delivery_method='pickup', payment_method='cash')

        self.assertEqual(self._order_snapshot(whatsapp_order), self._order_snapshot(checkout_order))
        self.assertEqual(whatsapp_order.metadata.get('source'), 'whatsapp')

    def test_default_delivery_order_shape_matches_checkout_service(self):
        checkout_order = self._checkout_order(delivery_method='delivery')
        whatsapp_order = self._whatsapp_order(delivery_method='delivery', payment_method='cash')

        self.assertEqual(self._order_snapshot(whatsapp_order), self._order_snapshot(checkout_order))
        self.assertEqual(whatsapp_order.metadata.get('source'), 'whatsapp')


class MessageDedupRegressionTest(TestCase):
    """Regression: context_message_id=None must filter by '' not skip the filter."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.whatsapp.models import WhatsAppAccount, Message
        from apps.whatsapp.repositories.message_repository import MessageRepository
        from django.utils import timezone

        User = get_user_model()
        owner = User.objects.create_user(
            username='dedup_owner', email='dedup@test.com', password='pass'
        )
        self.account = WhatsAppAccount.objects.create(
            name='Dedup Test Account',
            phone_number_id='dedup_pnid_001',
            waba_id='dedup_waba_001',
            phone_number='+5500000000001',
            access_token_encrypted='tok',
            owner=owner,
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )
        self.Message = Message
        self.repo = MessageRepository()
        self.to = '+5511999990000'
        self.text = 'Olá, seu pedido foi recebido!'
        self.since = timezone.now() - timedelta(seconds=10)

    def _make_message(self, context_id=''):
        from django.utils import timezone
        return self.Message.objects.create(
            account=self.account,
            direction=self.Message.MessageDirection.OUTBOUND,
            message_type=self.Message.MessageType.TEXT,
            to_number=self.to,
            text_body=self.text,
            context_message_id=context_id,
            status=self.Message.MessageStatus.SENT,
        )

    def test_none_context_id_matches_empty_string_message(self):
        """Passing context_message_id=None should match messages with context_message_id=''."""
        self._make_message(context_id='')
        result = self.repo.find_recent_outbound_text_duplicate(
            account=self.account,
            to_number=self.to,
            text_body=self.text,
            context_message_id=None,
            since=self.since,
        )
        self.assertIsNotNone(result)

    def test_different_context_ids_not_deduplicated(self):
        """A message with context_id='A' must not suppress a send with context_id='B'."""
        self._make_message(context_id='inbound-msg-A')
        result = self.repo.find_recent_outbound_text_duplicate(
            account=self.account,
            to_number=self.to,
            text_body=self.text,
            context_message_id='inbound-msg-B',
            since=self.since,
        )
        self.assertIsNone(result)

    def test_same_context_id_is_deduplicated(self):
        """Same context_id and same text within the window must be suppressed."""
        self._make_message(context_id='inbound-msg-X')
        result = self.repo.find_recent_outbound_text_duplicate(
            account=self.account,
            to_number=self.to,
            text_body=self.text,
            context_message_id='inbound-msg-X',
            since=self.since,
        )
        self.assertIsNotNone(result)
