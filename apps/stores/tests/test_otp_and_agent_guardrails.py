"""
Regression tests for OTP authentication and WhatsApp agent guardrails.

Covers:
- POST /api/v1/auth/whatsapp/send/ — gera e envia código OTP
- POST /api/v1/auth/whatsapp/verify/ — valida código e retorna token
- Agent guardrails: bot retorna fallback para mensagem vazia
- Agent guardrails: bot bloqueia intents fora do horário
- Agent guardrails: detector classifica intenções coloquiais corretamente
- Agent guardrails: dead_end counter incrementa em UNKNOWN consecutivos
"""
from unittest.mock import patch, MagicMock

from django.test import override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

_SETTINGS = dict(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework.authentication.TokenAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)


@override_settings(**_SETTINGS)
class WhatsAppOTPContractTest(APITestCase):
    """OTP send/verify endpoint contract tests."""

    PHONE = '+5563999990001'

    def tearDown(self):
        cache.clear()

    @patch('apps.core.auth.views._resolve_whatsapp_account_id', return_value='fake-account-id')
    @patch('apps.core.auth.views.WhatsAppAuthService.send_auth_code')
    def test_send_returns_200(self, mock_send, _mock_resolve):
        mock_send.return_value = {'success': True, 'message': 'Code sent'}
        r = self.client.post(
            '/api/v1/auth/whatsapp/send/',
            {'phone_number': self.PHONE},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        mock_send.assert_called_once()

    @patch('apps.core.auth.views._resolve_whatsapp_account_id', return_value='fake-account-id')
    @patch('apps.core.auth.views.WhatsAppAuthService.send_auth_code')
    def test_send_missing_phone_returns_400(self, mock_send, _mock_resolve):
        r = self.client.post('/api/v1/auth/whatsapp/send/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        mock_send.assert_not_called()

    @patch('apps.core.services.customer_identity.CustomerIdentityService.resolve_user')
    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_valid_code_returns_token(self, mock_verify, mock_resolve_user):
        user = User.objects.create_user('otp-user', 'otp@example.com', 'pw')
        profile_mock = MagicMock()
        profile_mock.phone = self.PHONE
        mock_resolve_user.return_value = (user, profile_mock, False)
        mock_verify.return_value = {
            'valid': True,
            'message': 'Autenticação realizada com sucesso',
            'user': {'name': 'Teste OTP'},
            'phone_number': self.PHONE,
        }
        r = self.client.post(
            '/api/v1/auth/whatsapp/verify/',
            {'phone_number': self.PHONE, 'code': '123456'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('token', r.json())

    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_invalid_code_returns_400(self, mock_verify):
        mock_verify.return_value = {
            'valid': False,
            'error': 'invalid_code',
            'message': 'Código incorreto.',
        }
        r = self.client.post(
            '/api/v1/auth/whatsapp/verify/',
            {'phone_number': self.PHONE, 'code': '000000'},
            format='json',
        )
        self.assertIn(r.status_code, (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        ))

    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_missing_fields_returns_400(self, mock_verify):
        r = self.client.post('/api/v1/auth/whatsapp/verify/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        mock_verify.assert_not_called()


@override_settings(**_SETTINGS)
class AgentGuardrailsTest(APITestCase):
    """
    Unit tests for WhatsApp bot guardrails via UnifiedService.

    Tests the service layer directly — not HTTP — to stay fast and deterministic.
    """

    def _make_service(self):
        from apps.automation.services.unified_service import UnifiedService

        conversation = MagicMock()
        conversation.id = 'bbbbbbbb-0000-0000-0000-000000000001'
        conversation.phone_number = '+5563000000099'
        conversation.mode = None  # not in human-handoff mode

        store = MagicMock()
        store.id = 'cccccccc-0000-0000-0000-000000000001'
        store.is_open.return_value = True

        svc = UnifiedService.__new__(UnifiedService)
        svc.account = MagicMock()
        svc.conversation = conversation
        svc.company = MagicMock()
        svc.store = store
        svc.detector = MagicMock()
        svc.use_llm = False
        svc.agent = None
        svc.debug = False
        svc.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}
        return svc

    def test_out_of_hours_blocks_create_order_intent(self):
        """CREATE_ORDER intent while store is closed must call _get_out_of_hours_response."""
        from apps.whatsapp.intents.detector import IntentType
        from apps.automation.services.unified_service import UnifiedService

        svc = self._make_service()
        svc.store.is_open.return_value = False
        svc.detector.detect.return_value = {
            'intent': IntentType.CREATE_ORDER,
            'method': 'regex',
            'confidence': 0.95,
            'entities': {},
            'original_message': 'quero pedir uma salada',
        }

        with (
            patch.object(svc, '_has_pending_delivery_address_session', return_value=False),
            patch.object(svc, '_has_pending_notes_session', return_value=False),
            patch.object(svc, '_message_matches_catalog_product', return_value=False),
            patch.object(svc, '_get_session_data', return_value={}),
            patch.object(svc, '_get_out_of_hours_response') as mock_ooh,
        ):
            mock_ooh.return_value = MagicMock(content='Estamos fechados agora.')
            svc.process_message('quero pedir uma salada')

        mock_ooh.assert_called_once()

    def test_empty_message_returns_fallback_not_none(self):
        """Empty message must return a UnifiedResponse (silent fallback), not None."""
        from apps.automation.services.unified_service import UnifiedService, UnifiedResponse

        svc = self._make_service()
        response = svc.process_message('')

        self.assertIsNotNone(response)
        self.assertIsInstance(response, UnifiedResponse)

    def test_intent_detector_classifies_cancel_colloquial(self):
        """Colloquial dismissals recognized by regex → CANCEL_ORDER (no LLM needed)."""
        from apps.whatsapp.intents.detector import IntentDetector, IntentType

        detector = IntentDetector(use_llm_fallback=False)
        for phrase in ['deixa pra la', 'nao quero mais', 'cancela', 'esquece']:
            result = detector.detect(phrase)
            self.assertEqual(
                result['intent'], IntentType.CANCEL_ORDER,
                f'Expected CANCEL_ORDER for "{phrase}", got {result["intent"]}'
            )

    def test_intent_detector_classifies_frustration(self):
        """Frustration phrase recognized by regex → FRUSTRATION (no LLM needed)."""
        from apps.whatsapp.intents.detector import IntentDetector, IntentType

        detector = IntentDetector(use_llm_fallback=False)
        result = detector.detect('isso nao funciona')
        self.assertEqual(
            result['intent'], IntentType.FRUSTRATION,
            f'Expected FRUSTRATION for "isso nao funciona", got {result["intent"]}'
        )

    def test_dead_end_counter_increments_on_unknown_intent(self):
        """UNKNOWN intent must call _increment_dead_end."""
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        svc = self._make_service()
        svc.detector.detect.return_value = {
            'intent': IntentType.UNKNOWN,
            'method': 'none',
            'confidence': 0.0,
            'entities': {},
            'original_message': 'xablau nao sei',
        }

        with (
            patch.object(svc, '_has_pending_delivery_address_session', return_value=False),
            patch.object(svc, '_has_pending_notes_session', return_value=False),
            patch.object(svc, '_message_matches_catalog_product', return_value=False),
            patch.object(svc, '_get_session_data', return_value={}),
            patch.object(svc, '_run_handler', return_value=None),
            patch.object(svc, '_get_template_for_intent', return_value=None),
            patch.object(svc, '_should_use_llm', return_value=False),
            patch.object(svc, '_increment_dead_end', return_value=1) as mock_inc,
        ):
            svc.process_message('xablau nao sei')

        mock_inc.assert_called_once()
