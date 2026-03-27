"""
Unit tests for CustomerIdentityService.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.core.services.customer_identity import CustomerIdentityService
from apps.core.models import UserProfile
from apps.stores.models import Store, StoreCustomer

User = get_user_model()


def _make_store(owner, slug='identity-store'):
    return Store.objects.create(
        owner=owner,
        name='Identity Test Store',
        slug=slug,
        is_active=True,
    )


class CustomerIdentityHelpersTest(TestCase):
    """Tests for static helper methods."""

    def test_digits_only_strips_non_digits(self):
        result = CustomerIdentityService.digits_only('+55 (11) 9999-8888')
        self.assertEqual(result, '551199998888')

    def test_digits_only_empty(self):
        self.assertEqual(CustomerIdentityService.digits_only(''), '')
        self.assertEqual(CustomerIdentityService.digits_only(None), '')

    def test_split_name_full(self):
        first, last = CustomerIdentityService.split_name('João da Silva')
        self.assertEqual(first, 'João')
        self.assertEqual(last, 'da Silva')

    def test_split_name_single(self):
        first, last = CustomerIdentityService.split_name('Maria')
        self.assertEqual(first, 'Maria')
        self.assertEqual(last, '')

    def test_split_name_empty(self):
        first, last = CustomerIdentityService.split_name('')
        self.assertEqual(first, '')
        self.assertEqual(last, '')

    def test_normalize_state_abbreviation(self):
        self.assertEqual(CustomerIdentityService.normalize_state('SP'), 'SP')
        self.assertEqual(CustomerIdentityService.normalize_state('sp'), 'SP')

    def test_normalize_state_full_name(self):
        result = CustomerIdentityService.normalize_state('São Paulo')
        self.assertEqual(len(result), 2)

    def test_phone_candidates_includes_normalized(self):
        candidates = CustomerIdentityService.phone_candidates('11999998888')
        self.assertTrue(len(candidates) > 1)
        # Should include the original and variations
        self.assertTrue(any('11999998888' in c for c in candidates))

    def test_generate_unique_username_unique(self):
        User.objects.create_user(username='cliente_test', email='a@test.com', password='x')
        username = CustomerIdentityService.generate_unique_username('cliente_test')
        self.assertNotEqual(username, 'cliente_test')
        self.assertFalse(User.objects.filter(username='cliente_test').count() > 1)


class CustomerIdentityResolveUserTest(TestCase):
    """Tests for resolve_user."""

    def test_creates_user_when_none_exists(self):
        user, profile, created = CustomerIdentityService.resolve_user(
            email='novo@test.com',
            phone='+5511999990001',
            full_name='Novo Cliente',
        )
        self.assertIsNotNone(user)
        self.assertTrue(created)
        self.assertEqual(user.first_name, 'Novo')

    def test_finds_existing_user_by_email(self):
        existing = User.objects.create_user(
            username='existing_user', email='existing@test.com', password='pass'
        )
        user, profile, created = CustomerIdentityService.resolve_user(
            email='existing@test.com',
        )
        self.assertEqual(user.id, existing.id)
        self.assertFalse(created)

    def test_phone_match_takes_priority_over_email(self):
        phone_user = User.objects.create_user(
            username='phone_user', email='phone@test.com', password='pass'
        )
        UserProfile.objects.filter(user=phone_user).update(phone='+5511999991111')
        email_user = User.objects.create_user(
            username='email_user', email='email@test.com', password='pass'
        )
        user, profile, created = CustomerIdentityService.resolve_user(
            email='email@test.com',
            phone='+5511999991111',
        )
        # Phone match wins
        self.assertEqual(user.id, phone_user.id)
        self.assertFalse(created)

    def test_returns_none_when_create_false_and_no_match(self):
        user, profile, created = CustomerIdentityService.resolve_user(
            email='ghost@test.com',
            create=False,
        )
        self.assertIsNone(user)
        self.assertIsNone(profile)

    def test_authenticated_user_returned_as_is(self):
        auth_user = User.objects.create_user(
            username='auth_user', email='auth@test.com', password='pass'
        )
        user, profile, created = CustomerIdentityService.resolve_user(
            email='other@test.com',
            user=auth_user,
        )
        self.assertEqual(user.id, auth_user.id)
        self.assertFalse(created)

    def test_created_user_has_placeholder_email_when_no_real_email(self):
        user, profile, created = CustomerIdentityService.resolve_user(
            phone='+5511888880000',
        )
        self.assertTrue(created)
        self.assertIn('@pastita.local', user.email)


class CustomerIdentitySyncCheckoutTest(TestCase):
    """Tests for sync_checkout_customer."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='sync_owner', email='sync@test.com', password='pass'
        )
        self.store = _make_store(self.owner)

    def test_creates_store_customer_on_checkout(self):
        result = CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Ana Souza',
            email='ana.souza@test.com',
            phone='+5511777770001',
        )
        self.assertIsNotNone(result['user'])
        self.assertIsNotNone(result['store_customer'])
        self.assertIsInstance(result['store_customer'], StoreCustomer)
        self.assertEqual(result['store_customer'].store, self.store)

    def test_reuses_existing_user_on_second_checkout(self):
        CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Carlos',
            email='carlos.r@test.com',
            phone='+5511666660001',
        )
        result2 = CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Carlos R',
            email='carlos.r@test.com',
            phone='+5511666660001',
        )
        self.assertFalse(result2['user_created'])
        # Only one StoreCustomer record
        count = StoreCustomer.objects.filter(store=self.store, user=result2['user']).count()
        self.assertEqual(count, 1)

    def test_delivery_address_stored_in_store_customer(self):
        result = CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Bruna',
            email='bruna@test.com',
            phone='+5511555550001',
            delivery_method='delivery',
            delivery_address={
                'street': 'Rua das Flores',
                'number': '42',
                'city': 'Campinas',
                'state': 'SP',
                'zip_code': '13000000',
            },
        )
        store_customer = result['store_customer']
        self.assertTrue(len(store_customer.addresses) > 0)
        self.assertIn('Rua das Flores', store_customer.addresses[0].get('street', ''))

    def test_pickup_delivery_does_not_store_address(self):
        result = CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Diego',
            email='diego@test.com',
            phone='+5511444440001',
            delivery_method='pickup',
            delivery_address={
                'street': 'Rua Qualquer',
                'number': '1',
            },
        )
        store_customer = result['store_customer']
        # For pickup, address should NOT be stored
        self.assertFalse(store_customer.addresses)


class CustomerIdentityBuildAddressTest(TestCase):
    """Tests for _build_address_record."""

    def test_formats_full_address(self):
        record = CustomerIdentityService._build_address_record({
            'street': 'Av. Paulista',
            'number': '1000',
            'complement': 'Apto 5',
            'neighborhood': 'Bela Vista',
            'city': 'São Paulo',
            'state': 'SP',
            'zip_code': '01310100',
        })
        self.assertIsNotNone(record)
        self.assertIn('Av. Paulista', record['formatted'])
        self.assertIn('São Paulo', record['formatted'])

    def test_returns_none_for_empty_address(self):
        record = CustomerIdentityService._build_address_record({})
        self.assertIsNone(record)

    def test_strips_zip_code_to_digits_only(self):
        record = CustomerIdentityService._build_address_record({
            'street': 'Rua A',
            'zip_code': '01310-100',
        })
        self.assertEqual(record['zip_code'], '01310100')
