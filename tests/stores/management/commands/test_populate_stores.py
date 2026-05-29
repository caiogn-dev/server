"""
Integration tests for store population commands.
"""
from decimal import Decimal
from django.test import TestCase
from django.core.management import call_command
from io import StringIO

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreDeliveryZone
from apps.whatsapp.models import WhatsAppAccount
from django.contrib.auth import get_user_model

User = get_user_model()


class PopulateCeSaladasTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='test')

    def test_populate_ce_saladas_creates_store(self):
        call_command('populate_ce_saladas_menu')
        self.assertTrue(Store.objects.filter(slug='ce-saladas').exists())
        store = Store.objects.get(slug='ce-saladas')
        self.assertEqual(store.name, 'Cê Saladas')
        self.assertEqual(store.primary_color, '#2E7D32')

    def test_populate_ce_saladas_creates_whatsapp_account(self):
        call_command('populate_ce_saladas_menu')
        self.assertTrue(WhatsAppAccount.objects.filter(waba_id='1537842617304215').exists())
        wa = WhatsAppAccount.objects.get(waba_id='1537842617304215')
        self.assertEqual(wa.phone_number, '63991386719')
        self.assertTrue(wa.auto_response_enabled)

    def test_populate_ce_saladas_creates_categories(self):
        call_command('populate_ce_saladas_menu')
        store = Store.objects.get(slug='ce-saladas')
        categories = StoreCategory.objects.filter(store=store)
        self.assertEqual(categories.count(), 1)
        self.assertTrue(categories.filter(slug='saladas').exists())

    def test_populate_ce_saladas_creates_products(self):
        call_command('populate_ce_saladas_menu')
        store = Store.objects.get(slug='ce-saladas')
        products = StoreProduct.objects.filter(store=store)
        self.assertEqual(products.count(), 7)
        self.assertTrue(products.filter(sku='CS-TIL').exists())

    def test_populate_ce_saladas_creates_delivery_zones(self):
        call_command('populate_ce_saladas_menu')
        store = Store.objects.get(slug='ce-saladas')
        zones = StoreDeliveryZone.objects.filter(store=store)
        self.assertEqual(zones.count(), 16)
        zone0 = zones.filter(distance_band='0-2').first()
        self.assertEqual(zone0.delivery_fee, Decimal('7.00'))

    def test_populate_ce_saladas_idempotent(self):
        call_command('populate_ce_saladas_menu')
        count_first = StoreProduct.objects.filter(store__slug='ce-saladas').count()
        call_command('populate_ce_saladas_menu', '--force')
        count_second = StoreProduct.objects.filter(store__slug='ce-saladas').count()
        self.assertEqual(count_first, count_second)


class PopulatePastitaTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='test')

    def test_populate_pastita_creates_store(self):
        call_command('populate_pastita_menu')
        self.assertTrue(Store.objects.filter(slug='pastita').exists())
        store = Store.objects.get(slug='pastita')
        self.assertEqual(store.name, 'Pastita')

    def test_populate_pastita_creates_categories(self):
        call_command('populate_pastita_menu')
        store = Store.objects.get(slug='pastita')
        categories = StoreCategory.objects.filter(store=store)
        self.assertGreater(categories.count(), 0)

    def test_populate_pastita_creates_products(self):
        call_command('populate_pastita_menu')
        store = Store.objects.get(slug='pastita')
        products = StoreProduct.objects.filter(store=store)
        self.assertGreater(products.count(), 0)

    def test_populate_pastita_creates_delivery_zones(self):
        call_command('populate_pastita_menu')
        store = Store.objects.get(slug='pastita')
        zones = StoreDeliveryZone.objects.filter(store=store)
        self.assertEqual(zones.count(), 16)


class PopulateKeroKeroTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='test')

    def test_populate_kero_kero_creates_store(self):
        call_command('populate_kero_kero_menu')
        self.assertTrue(Store.objects.filter(slug='kero-kero').exists())
        store = Store.objects.get(slug='kero-kero')
        self.assertEqual(store.name, 'Kero Kero')

    def test_populate_kero_kero_creates_categories(self):
        call_command('populate_kero_kero_menu')
        store = Store.objects.get(slug='kero-kero')
        categories = StoreCategory.objects.filter(store=store)
        self.assertEqual(categories.count(), 8)

    def test_populate_kero_kero_creates_products(self):
        call_command('populate_kero_kero_menu')
        store = Store.objects.get(slug='kero-kero')
        products = StoreProduct.objects.filter(store=store)
        self.assertGreater(products.count(), 0)

    def test_populate_kero_kero_creates_delivery_zones(self):
        call_command('populate_kero_kero_menu')
        store = Store.objects.get(slug='kero-kero')
        zones = StoreDeliveryZone.objects.filter(store=store)
        self.assertEqual(zones.count(), 16)


class PopulateAllStoresTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='admin@test.com', password='test')

    def test_populate_all_stores_creates_all_three(self):
        call_command('populate_all_stores', '--all')
        self.assertEqual(Store.objects.filter(slug='ce-saladas').count(), 1)
        self.assertEqual(Store.objects.filter(slug='pastita').count(), 1)
        self.assertEqual(Store.objects.filter(slug='kero-kero').count(), 1)

    def test_populate_specific_store_only(self):
        call_command('populate_all_stores', '--store=ce-saladas')
        self.assertEqual(Store.objects.filter(slug='ce-saladas').count(), 1)
        self.assertEqual(Store.objects.filter(slug='pastita').count(), 0)
        self.assertEqual(Store.objects.filter(slug='kero-kero').count(), 0)
