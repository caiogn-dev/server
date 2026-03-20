"""
Tests for the Automation app:
- CompanyProfile CRUD and store sync
- AutoMessage rendering
- CustomerSession lifecycle
- Automation API endpoints
"""
import uuid
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
        # is_ai_enabled is a regular method, not a property
        result = profile.is_ai_enabled()
        self.assertIsInstance(result, bool)

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
        # Signal creates defaults; use a unique name to avoid unique_together clash
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Custom Test Message',
            message_text='Seu pedido foi confirmado, {customer_name}!',
            is_active=True,
        )
        self.assertIsNotNone(msg.pk)
        self.assertEqual(msg.company, self.profile)

    def test_render_message_interpolates_context(self):
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_READY,
            name='Welcome Render Test',
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
            event_type=AutoMessage.EventType.ORDER_READY,
            name='Missing Key Test',
            message_text='Olá, {customer_name}!',
            is_active=True,
        )
        try:
            rendered = msg.render_message({})
            self.assertIsInstance(rendered, str)
        except (KeyError, IndexError):
            self.fail('render_message raised on missing context key')

    def test_inactive_message_is_excluded_from_filter(self):
        """Inactive messages must be filterable by is_active=False."""
        unique_name = f'Inactive-{uuid.uuid4().hex[:8]}'
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_READY,
            name=unique_name,
            message_text='Inactive',
            is_active=False,
        )
        # Filtering by is_active=False should include it
        inactive = AutoMessage.objects.filter(company=self.profile, is_active=False, name=unique_name)
        self.assertEqual(inactive.count(), 1)
        # Filtering by is_active=True should exclude it
        active = AutoMessage.objects.filter(company=self.profile, is_active=True, name=unique_name)
        self.assertEqual(active.count(), 0)

    def test_str_representation(self):
        """AutoMessage __str__ returns '{company_name} - {event_type_display}'."""
        msg = AutoMessage.objects.create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_CONFIRMED,
            name='Str Test Msg',
            message_text='Hello',
            is_active=True,
        )
        # str(msg) = "StoreName - EventTypeDisplay"
        self.assertIn(self.profile.company_name, str(msg))


# ---------------------------------------------------------------------------
# CustomerSession model tests
# ---------------------------------------------------------------------------

class CustomerSessionModelTestCase(TestCase):

    def setUp(self):
        self.owner = _make_user('session_owner')
        self.store = _make_store(self.owner, slug='session-store')
        self.profile = _make_company_profile(self.store)

    def _make_session(self, phone='+5511999990001', session_id=None):
        return CustomerSession.objects.create(
            company=self.profile,
            phone_number=phone,
            session_id=session_id or str(uuid.uuid4()),
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
        self.assertIn(cart, [{}, None, []])

    def test_add_notification(self):
        session = self._make_session()
        session.add_notification('order_confirmed')
        self.assertTrue(session.was_notification_sent('order_confirmed'))

    def test_notification_not_sent_by_default(self):
        session = self._make_session()
        self.assertFalse(session.was_notification_sent('order_confirmed'))

    def test_two_sessions_same_phone_different_session_ids(self):
        """The same phone can have multiple sessions with different session_ids."""
        s1 = self._make_session(phone='+5511777770001')
        s2 = self._make_session(phone='+5511777770001')
        self.assertNotEqual(s1.session_id, s2.session_id)
        self.assertIsNotNone(s2.pk)

    def test_duplicate_session_id_raises_error(self):
        """session_id is unique — duplicate raises IntegrityError."""
        sid = str(uuid.uuid4())
        self._make_session(session_id=sid)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            self._make_session(session_id=sid)


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
        # The create serializer expects company_id (UUID), not company (FK)
        payload = {
            'company_id': str(self.profile.pk),
            'event_type': AutoMessage.EventType.ORDER_READY,
            'name': 'API Created Message',
            'message_text': 'Your order is ready!',
            'is_active': True,
        }
        resp = self.client.post('/api/v1/automation/messages/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

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

    def test_unified_stats_requires_account_id(self):
        """UnifiedStatsView requires account_id query param — returns 400 without it."""
        resp = self.client.get('/api/v1/automation/unified/stats/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unified_stats_unauthenticated(self):
        self.client.credentials()
        resp = self.client.get('/api/v1/automation/unified/stats/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
