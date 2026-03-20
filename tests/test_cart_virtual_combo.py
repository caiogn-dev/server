"""
Tests for virtual combo (salad builder) cart and checkout flow.

Covers:
- Adding a virtual combo (no FK to StoreCombo) via cart/add/
- Checkout succeeds when cart contains only a virtual combo
- checkout_service uses effective_name / effective_price for virtual combos
- StoreOrderItem created correctly for virtual combo
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCart, StoreCartComboItem
from apps.stores.services import cart_service, checkout_service

User = get_user_model()


class VirtualComboCartTestCase(TestCase):
    """Test that virtual combos (salad builder) can be added to and checked out from cart."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='salad-test-user',
            email='salad@example.com',
            password='testpass123',
        )
        self.store = Store.objects.create(
            name='CE Saladas',
            slug='ce-saladas-vcombo-test',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
            currency='BRL',
        )
        self.cart_key = 'test-salad-cart-key-001'

    # ─── Service-level tests ───────────────────────────────────────────────────

    def _get_cart(self):
        return cart_service.get_or_create_cart(self.store, user=None, session_key=self.cart_key)

    def test_add_virtual_combo_creates_cart_item(self):
        cart = self._get_cart()
        cart_service.add_combo(
            cart,
            combo=None,
            combo_name='Monte sua Salada',
            unit_price=Decimal('29.90'),
            customizations={'is_salad_builder': True, 'ingredients': []},
            notes='Base: Rúcula | Proteína: Frango',
        )
        self.assertEqual(cart.combo_items.count(), 1)
        item = cart.combo_items.first()
        self.assertIsNone(item.combo)
        self.assertEqual(item.combo_name, 'Monte sua Salada')
        self.assertEqual(item.effective_name, 'Monte sua Salada')
        self.assertEqual(item.effective_price, Decimal('29.90'))
        self.assertEqual(item.subtotal, Decimal('29.90'))

    def test_effective_name_falls_back_to_default(self):
        # Unsaved instance (no DB hit) to test the property
        item = StoreCartComboItem()
        item.combo = None
        item.combo_name = ''
        self.assertEqual(item.effective_name, 'Combo')

    def test_virtual_combo_subtotal_correct(self):
        cart = self._get_cart()
        cart_service.add_combo(
            cart,
            combo=None,
            combo_name='Salada Especial',
            unit_price=Decimal('35.00'),
            quantity=2,
        )
        item = cart.combo_items.first()
        self.assertEqual(item.subtotal, Decimal('70.00'))

    def test_checkout_with_only_virtual_combo(self):
        """Checkout should succeed when cart has only a virtual combo (no real combo FK)."""
        cart = self._get_cart()
        cart_service.add_combo(
            cart,
            combo=None,
            combo_name='Monte sua Salada',
            unit_price=Decimal('29.90'),
            notes='Base: Rúcula | Proteína: Frango | Molho: Tahini',
        )
        self.assertTrue(cart.combo_items.exists())
        self.assertFalse(cart.items.exists())

        order = checkout_service.create_order(
            cart=cart,
            customer_data={
                'name': 'João Salada',
                'email': 'joao@example.com',
                'phone': '61999999999',
            },
            delivery_data={'method': 'pickup', 'address': {}, 'notes': ''},
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        self.assertEqual(item.product_name, 'Monte sua Salada')
        self.assertEqual(item.unit_price, Decimal('29.90'))
        self.assertIn('Rúcula', item.notes or '')

    # ─── API-level tests ───────────────────────────────────────────────────────

    def test_cart_add_virtual_combo_api(self):
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add/',
            data={
                'combo_name': 'Monte sua Salada',
                'unit_price': '29.90',
                'quantity': 1,
                'customizations': {'is_salad_builder': True},
                'notes': 'Base: Rúcula',
                'cart_key': self.cart_key,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        combo_items = data.get('combo_items', [])
        self.assertEqual(len(combo_items), 1)
        self.assertEqual(combo_items[0]['combo_name'], 'Monte sua Salada')

    def test_checkout_empty_cart_returns_400(self):
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            data={
                'customer_name': 'Test',
                'customer_email': 'test@example.com',
                'customer_phone': '61900000000',
                'shipping_method': 'pickup',
                'payment_method': 'pix',
                'cart_key': 'empty-cart-key-999',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('empty', response.json().get('error', '').lower())

    def test_checkout_with_virtual_combo_api(self):
        # First add the salad
        self.client.post(
            f'/api/v1/stores/{self.store.slug}/cart/add/',
            data={
                'combo_name': 'Monte sua Salada',
                'unit_price': '29.90',
                'quantity': 1,
                'cart_key': self.cart_key,
            },
            format='json',
        )
        # Then checkout (cash avoids needing payment gateway credentials in test)
        response = self.client.post(
            f'/api/v1/stores/{self.store.slug}/checkout/',
            data={
                'customer_name': 'João Salada',
                'customer_email': 'joao@example.com',
                'customer_phone': '61999999999',
                'shipping_method': 'pickup',
                'delivery_method': 'pickup',
                'payment_method': 'cash',
                'cart_key': self.cart_key,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('order_number', data)
