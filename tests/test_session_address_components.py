"""
Testes: fluxo de address_components na sessão WhatsApp.

Cobertura:
1. save_delivery_address_info persiste address_components no cart_data
2. get_delivery_address_info retorna address_components corretamente
3. Ausência de components não causa erro (campo opcional)
4. _build_delivery_address em WhatsAppOrderService usa components da sessão
5. Pedido criado a partir de sessão tem delivery_address com campos estruturados

Executar:
    python manage.py test tests.test_session_address_components --keepdb -v 2
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreProduct, StoreOrder
from apps.automation.models import CustomerSession, CompanyProfile

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass',
    )


def _make_store(owner, slug='sac-test'):
    return Store.objects.create(
        owner=owner,
        name='SAC Test Store',
        slug=slug,
        is_active=True,
        status='active',
        default_delivery_fee=Decimal('8.00'),
    )


def _make_session(store, phone='+5563999990010'):
    profile, _ = CompanyProfile.objects.get_or_create(
        store=store,
        defaults={'company_name': 'Test'},
    )
    return CustomerSession.objects.create(
        company=profile,
        phone_number=phone,
        status=CustomerSession.SessionStatus.ACTIVE,
        cart_data={},
    )


# ─── Testes: SessionManager.save_delivery_address_info ───────────────────────

class SaveDeliveryAddressInfoTest(TestCase):
    """
    Garante que save_delivery_address_info persiste address_components
    no campo cart_data da sessão.
    """

    def setUp(self):
        owner = _make_user('sdai_owner')
        self.store = _make_store(owner, 'sdai-store')
        self.session = _make_session(self.store, '+5563900000010')

    def _make_manager(self):
        from apps.automation.services.session_manager import SessionManager
        mgr = SessionManager(
            store=self.store,
            phone_number=self.session.phone_number,
        )
        return mgr

    def test_address_components_saved_in_cart_data(self):
        mgr = self._make_manager()
        components = {
            'street': 'Rua das Flores',
            'house_number': '42',
            'neighborhood': 'Centro',
            'city': 'Palmas',
            'state_code': 'TO',
            'zip_code': '77000-000',
        }
        mgr.save_delivery_address_info(
            address='Rua das Flores, 42',
            fee=10.0,
            lat=-10.18,
            lng=-48.33,
            address_components=components,
        )

        self.session.refresh_from_db()
        saved = self.session.cart_data.get('delivery_address_components', {})
        self.assertEqual(saved['street'], 'Rua das Flores')
        self.assertEqual(saved['city'], 'Palmas')
        self.assertEqual(saved['zip_code'], '77000-000')

    def test_no_components_does_not_set_key(self):
        """address_components=None não grava a chave no cart_data."""
        mgr = self._make_manager()
        mgr.save_delivery_address_info(
            address='Sem componentes',
            fee=5.0,
            address_components=None,
        )

        self.session.refresh_from_db()
        self.assertNotIn('delivery_address_components', self.session.cart_data)

    def test_empty_components_dict_does_not_set_key(self):
        """address_components={} (falsy) não grava a chave no cart_data."""
        mgr = self._make_manager()
        mgr.save_delivery_address_info(
            address='Sem componentes',
            fee=5.0,
            address_components={},
        )

        self.session.refresh_from_db()
        self.assertNotIn('delivery_address_components', self.session.cart_data)


# ─── Testes: SessionManager.get_delivery_address_info ────────────────────────

class GetDeliveryAddressInfoTest(TestCase):
    """
    Verifica que get_delivery_address_info retorna address_components
    quando presentes e dicionário vazio quando ausentes.
    """

    def setUp(self):
        owner = _make_user('gdai_owner')
        self.store = _make_store(owner, 'gdai-store')
        self.session = _make_session(self.store, '+5563900000011')

    def _make_manager(self):
        from apps.automation.services.session_manager import SessionManager
        return SessionManager(store=self.store, phone_number=self.session.phone_number)

    def test_returns_components_when_present(self):
        self.session.cart_data = {
            'delivery_address': 'Alameda 1, 5',
            'delivery_fee_calculated': 9.0,
            'delivery_address_components': {
                'street': 'Alameda 1',
                'city': 'Palmas',
                'state_code': 'TO',
            },
        }
        self.session.save(update_fields=['cart_data'])

        info = self._make_manager().get_delivery_address_info()
        self.assertEqual(info['address_components']['city'], 'Palmas')
        self.assertEqual(info['address_components']['state_code'], 'TO')

    def test_returns_empty_dict_when_no_components(self):
        self.session.cart_data = {
            'delivery_address': 'Rua X',
            'delivery_fee_calculated': 8.0,
        }
        self.session.save(update_fields=['cart_data'])

        info = self._make_manager().get_delivery_address_info()
        self.assertEqual(info['address_components'], {})

    def test_returns_safe_defaults_when_session_empty(self):
        info = self._make_manager().get_delivery_address_info()
        self.assertEqual(info['address'], '')
        self.assertIsNone(info['fee'])
        self.assertEqual(info['address_components'], {})


# ─── Testes: criação de pedido usa components da sessão ──────────────────────

_PATCH_PAYMENT   = 'apps.whatsapp.services.order_service.CheckoutService.create_payment'
_PATCH_BROADCAST = 'apps.whatsapp.services.order_service.broadcast_order_event'


class OrderCreationUsesSessionComponentsTest(TestCase):
    """
    Verifica que WhatsAppOrderService.create_order_from_cart constrói
    delivery_address usando os componentes salvos na sessão, resultando
    em campos estruturados (street, city, state) no pedido criado.
    """

    def setUp(self):
        owner = _make_user('ocusc_owner')
        self.store = _make_store(owner, 'ocusc-store')
        self.product = StoreProduct.objects.create(
            store=self.store,
            name='Item',
            price=Decimal('10.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
        )

    def _call(self, addr_info=None):
        from apps.whatsapp.services.order_service import WhatsAppOrderService
        svc = WhatsAppOrderService(
            store=self.store,
            phone_number='+5563900000012',
            customer_name='Maria',
        )
        items = [{'product_id': str(self.product.id), 'quantity': 1}]
        with patch(_PATCH_PAYMENT, return_value={'success': True}), \
             patch(_PATCH_BROADCAST), \
             patch.object(svc, '_update_session'):
            return svc.create_order_from_cart(
                items=items,
                delivery_method='delivery',
                payment_method='cash',
                delivery_fee_override=8.0,
                delivery_address='Rua das Flores, 42',
                addr_info=addr_info,
            )

    def test_structured_components_appear_in_order_delivery_address(self):
        addr_info = {
            'lat': -10.18, 'lng': -48.33,
            'distance_km': 3.0, 'duration_minutes': 10,
            'address_components': {
                'street': 'Rua das Flores',
                'house_number': '42',
                'neighborhood': 'Centro',
                'city': 'Palmas',
                'state_code': 'TO',
                'zip_code': '77000-000',
            },
        }
        result = self._call(addr_info=addr_info)
        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(order_number=result['order_number'])
        da = order.delivery_address
        self.assertIsInstance(da, dict)
        self.assertEqual(da.get('street'), 'Rua das Flores')
        self.assertEqual(da.get('city'), 'Palmas')
        self.assertEqual(da.get('state'), 'TO')
        self.assertEqual(da.get('zip_code'), '77000-000')
        self.assertEqual(da.get('raw_address'), 'Rua das Flores, 42')

    def test_geo_coordinates_present_in_delivery_address(self):
        addr_info = {'lat': -10.18, 'lng': -48.33, 'distance_km': 3.0, 'duration_minutes': 10}
        result = self._call(addr_info=addr_info)
        order = StoreOrder.objects.get(order_number=result['order_number'])
        da = order.delivery_address
        self.assertEqual(da.get('lat'), -10.18)
        self.assertEqual(da.get('lng'), -48.33)

    def test_no_addr_info_stores_raw_address_only(self):
        result = self._call(addr_info=None)
        order = StoreOrder.objects.get(order_number=result['order_number'])
        da = order.delivery_address
        self.assertEqual(da.get('raw_address'), 'Rua das Flores, 42')
        self.assertNotIn('street', da)
