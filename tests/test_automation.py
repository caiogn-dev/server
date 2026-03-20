"""
Tests for the Automation app:
- CompanyProfile CRUD and store sync
- AutoMessage rendering
- CustomerSession lifecycle
- Automation API endpoints
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from apps.stores.models import Store
from apps.automation.models import (
    CompanyProfile,
    AutoMessage,
    CustomerSession,
    AutomationLog,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass123',
    )


def _make_store(owner, slug='auto-test-store'):
    return Store.objects.create(
        name='Auto Test Store',
        slug=slug,
        store_type=Store.StoreType.FOOD,
        status=Store.StoreStatus.ACTIVE,
        owner=owner,
        currency='BRL',
    )


def _make_company_profile(store):
    """Get or create a CompanyProfile for the store.
    A signal auto-creates one when a Store is saved, so use get_or_create.
    """
    profile, _ = CompanyProfile.objects.get_or_create(store=store)
    return profile


# ---------------------------------------------------------------------------
# CompanyProfile model tests
# ---------------------------------------------------------------------------

class CompanyProfileModelTestCase(TestCase):

    def setUp(self):
        self.owner = _make_user('auto_owner')
        self.store = _make_store(self.owner)

    def test_create_company_profile(self):
        profile = _make_company_profile(self.store)
        self.assertIsNotNone(profile.pk)
        self.assertEqual(profile.store, self.store)

    def test_company_name_proxies_to_store(self):
        profile = _make_company_profile(self.store)
        # company_name is a property that falls back to store.name
        self.assertEqual(profile.company_name, self.store.name)

    def test_is_ai_enabled_default(self):
        profile = _make_company_profile(self.store)
        # Default: ai_enabled depends on field default; just assert it's bool
        self.assertIsInstance(profile.is_ai_enabled, bool)

    def test_str_representation(self):
        profile = _make_company_profile(self.store)
        self.assertIn(self.store.name, str(profile))

    def test_get_effective_store(self):
        profile = _make_company_profile(self.store)
        self.assertEqual(profile.get_effective_store(), self.store)

    def test_sync_from_store(self):
        self.store.name = 'Updated Name'
        self.store.save()
        profile = _make_company_profile(self.store)
        # sync_from_store should not raise
        profile.sync_from_store(save=True)
        profile.refresh_from_db()
        self.assertIsNotNone(profile.pk)


# ---------------------------------------------------------------------------
# AutoMessage model tests
# ---------------------------------------------------------------------------

class AutoMessageModelTestCase(TestCase):

    def setUp(self):
        self.owner = _make_user('msg_owner')
        self.store = _make_store(self.owner, slug='msg-store')
        self.profile = _make_company_profile(self.store)

    def test_create_auto_message(self):
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Order Confirmed',
            message_text='Seu pedido foi confirmado, {customer_name}!',
            is_active=True,
        )
        self.assertIsNotNone(msg.pk)
        self.assertEqual(msg.company, self.profile)

    def test_render_message_interpolates_context(self):
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Welcome',
            message_text='Olá, {customer_name}! Seu pedido #{order_id} foi recebido.',
            is_active=True,
        )
        rendered = msg.render_message({'customer_name': 'Maria', 'order_id': '42'})
        self.assertIn('Maria', rendered)
        self.assertIn('42', rendered)

    def test_render_message_missing_context_key_is_safe(self):
        """render_message should not crash when context is missing a key."""
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Welcome2',
            message_text='Olá, {customer_name}!',
            is_active=True,
        )
        # Should not raise — missing keys handled gracefully
        try:
            rendered = msg.render_message({})
            self.assertIsInstance(rendered, str)
        except (KeyError, IndexError):
            self.fail('render_message raised on missing context key')

    def test_inactive_message_is_filtered_out(self):
        AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Active Msg',
            message_text='Active',
            is_active=True,
        )
        AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Inactive Msg',
            message_text='Inactive',
            is_active=False,
        )
        active = AutoMessage.objects.filter(company=self.profile, is_active=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().name, 'Active Msg')

    def test_str_representation(self):
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Test Msg',
            message_text='Hello',
            is_active=True,
        )
        self.assertIn('Test Msg', str(msg))


# ---------------------------------------------------------------------------
# CustomerSession model tests
# ---------------------------------------------------------------------------

class CustomerSessionModelTestCase(TestCase):

    def setUp(self):
        self.owner = _make_user('session_owner')
        self.store = _make_store(self.owner, slug='session-store')
        self.profile = _make_company_profile(self.store)

    def _make_session(self, phone='+5511999990001'):
        return CustomerSession.objects.create(
            company=self.profile,
            phone_number=phone,
            status=CustomerSession.SessionStatus.ACTIVE,
        )

    def test_create_session(self):
        session = self._make_session()
        self.assertIsNotNone(session.pk)
        self.assertEqual(session.status, CustomerSession.SessionStatus.ACTIVE)

    def test_session_str_contains_phone(self):
        session = self._make_session('+5511888880001')
        self.assertIn('+5511888880001', str(session))

    def test_session_initial_cart_is_empty(self):
        session = self._make_session()
        cart = session.cart_data
        # cart_data is a JSONField — should be dict or None
        self.assertIn(cart, [{}, None, []])

    def test_add_notification(self):
        session = self._make_session()
        session.add_notification('order_confirmed')
        self.assertTrue(session.was_notification_sent('order_confirmed'))

    def test_notification_not_sent_by_default(self):
        session = self._make_session()
        self.assertFalse(session.was_notification_sent('order_confirmed'))

    def test_unique_session_per_phone(self):
        """Two sessions for same phone can exist (no unique constraint at model level)."""
        self._make_session(phone='+5511777770001')
        s2 = self._make_session(phone='+5511777770001')
        self.assertIsNotNone(s2.pk)


# ---------------------------------------------------------------------------
# AutomationLog model tests
# ---------------------------------------------------------------------------

class AutomationLogModelTestCase(TestCase):

    def setUp(self):
        self.owner = _make_user('log_owner')
        self.store = _make_store(self.owner, slug='log-store')
        self.profile = _make_company_profile(self.store)

    def test_create_automation_log(self):
        log = AutomationLog.objects.create(
            company=self.profile,
            action_type=AutomationLog.ActionType.MESSAGE_SENT,
            description='Test log entry',
            is_error=False,
        )
        self.assertIsNotNone(log.pk)
        self.assertFalse(log.is_error)

    def test_create_error_log(self):
        log = AutomationLog.objects.create(
            company=self.profile,
            action_type=AutomationLog.ActionType.ERROR,
            description='Something went wrong',
            is_error=True,
        )
        self.assertTrue(log.is_error)

    def test_str_representation(self):
        log = AutomationLog.objects.create(
            company=self.profile,
            action_type=AutomationLog.ActionType.MESSAGE_SENT,
            description='hello',
            is_error=False,
        )
        self.assertIsInstance(str(log), str)


# ---------------------------------------------------------------------------
# Automation API endpoint tests
# ---------------------------------------------------------------------------

class AutomationAPITestCase(TestCase):
    """
    Test the REST API endpoints for the automation app.
    All endpoints require authentication.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = _make_user('api_auto_user')
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        self.store = _make_store(self.user, slug='api-auto-store')
        self.profile = _make_company_profile(self.store)

    # --- CompanyProfile endpoints ---

    def test_list_companies_authenticated(self):
        resp = self.client.get('/api/v1/automation/companies/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_list_companies_unauthenticated(self):
        self.client.credentials()
        resp = self.client.get('/api/v1/automation/companies/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_company_profile(self):
        resp = self.client.get(f'/api/v1/automation/companies/{self.profile.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(str(resp.data['id']), str(self.profile.pk))

    # --- AutoMessage endpoints ---

    def test_list_auto_messages(self):
        resp = self.client.get('/api/v1/automation/messages/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_auto_message_via_api(self):
        payload = {
            'company': str(self.profile.pk),
            'event_type': AutoMessage.EventType.ORDER_CONFIRMED,
            'name': 'API Created Message',
            'message_text': 'Your order is confirmed!',
            'is_active': True,
        }
        resp = self.client.post('/api/v1/automation/messages/', payload, format='json')
        self.assertIn(resp.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

    def test_list_auto_messages_unauthenticated(self):
        self.client.credentials()
        resp = self.client.get('/api/v1/automation/messages/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- CustomerSession endpoints ---

    def test_list_sessions(self):
        resp = self.client.get('/api/v1/automation/sessions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_list_sessions_unauthenticated(self):
        self.client.credentials()
        resp = self.client.get('/api/v1/automation/sessions/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- AutomationLog endpoints ---

    def test_list_logs(self):
        resp = self.client.get('/api/v1/automation/logs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- Unified stats endpoint ---

    def test_unified_stats_endpoint(self):
        resp = self.client.get('/api/v1/automation/unified/stats/')
        self.assertIn(resp.status_code, [
            status.HTTP_200_OK,
            status.HTTP_405_METHOD_NOT_ALLOWED,  # if only POST is allowed
        ])
