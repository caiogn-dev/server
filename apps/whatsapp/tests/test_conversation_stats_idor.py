"""
Regressão de segurança: IDOR em conversation_history e stats do MessageViewSet
+ info-disclosure via str(exc) em embedded_signup.

Problemas:
  1. conversation_history: any authenticated user can read WhatsApp messages
     from any account by passing a victim's account_id — _check_account_access
     is called for every other action but was missing here.
  2. stats: same omission for message statistics.
  3. embedded_signup: generic Exception handler returns f'Falha no onboarding: {exc}',
     which leaks Meta OAuth tokens and internal API error details.

Todos os testes são SimpleTestCase (sem DB/Docker).
"""
import inspect
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import PermissionDenied


@override_settings(
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class ConversationHistoryIDORTest(SimpleTestCase):
    """conversation_history deve chamar _check_account_access antes do serviço."""

    def _conversation_history_src(self):
        from apps.whatsapp.api.views import MessageViewSet
        return inspect.getsource(MessageViewSet.conversation_history)

    def test_check_account_access_presente_em_conversation_history(self):
        """`_check_account_access` deve aparecer na implementação de conversation_history."""
        src = self._conversation_history_src()
        self.assertIn(
            '_check_account_access',
            src,
            "conversation_history não chama _check_account_access — IDOR: "
            "qualquer autenticado lê histórico de mensagens de qualquer tenant.",
        )

    def test_check_aparece_antes_do_get_conversation_history(self):
        """O gate de acesso deve ser chamado ANTES de get_conversation_history."""
        src = self._conversation_history_src()
        pos_check = src.find('_check_account_access')
        pos_service = src.find('get_conversation_history')
        self.assertGreater(pos_check, -1, "Gate _check_account_access ausente em conversation_history")
        self.assertGreater(pos_service, -1, "get_conversation_history não encontrado no método")
        self.assertLess(
            pos_check,
            pos_service,
            "_check_account_access deve vir antes de get_conversation_history",
        )

    def test_conversation_history_nega_acesso_sem_permissao(self):
        """Usuário sem acesso à conta recebe PermissionDenied."""
        from apps.whatsapp.api.views import MessageViewSet

        viewset = MessageViewSet()
        mock_user = MagicMock()
        mock_user.is_superuser = False

        mock_request = MagicMock()
        mock_request.user = mock_user
        viewset.request = mock_request
        viewset.format_kwarg = None

        victim_account_id = '11111111-0000-0000-0000-000000000001'
        validated = {
            'account_id': victim_account_id,
            'phone_number': '+5511999990000',
            'limit': 50,
        }

        with patch('apps.whatsapp.api.views.ConversationHistorySerializer') as MockSer, \
             patch('apps.whatsapp.api.views.accessible_whatsapp_account_ids',
                   return_value=[]) as mock_gate, \
             patch('apps.whatsapp.api.views.MessageService') as MockMsgSvc:
            MockSer.return_value.is_valid = lambda raise_exception=False: True
            MockSer.return_value.validated_data = validated
            MockMsgSvc.return_value.get_conversation_history.return_value = []

            with self.assertRaises(PermissionDenied):
                viewset.conversation_history(mock_request)

            mock_gate.assert_called_once_with(mock_user)


@override_settings(
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class StatsIDORTest(SimpleTestCase):
    """stats deve chamar _check_account_access antes do serviço."""

    def _stats_src(self):
        from apps.whatsapp.api.views import MessageViewSet
        return inspect.getsource(MessageViewSet.stats)

    def test_check_account_access_presente_em_stats(self):
        """`_check_account_access` deve aparecer na implementação de stats."""
        src = self._stats_src()
        self.assertIn(
            '_check_account_access',
            src,
            "stats não chama _check_account_access — IDOR: "
            "qualquer autenticado lê métricas de qualquer conta WhatsApp.",
        )

    def test_check_aparece_antes_do_get_message_stats(self):
        """O gate de acesso deve ser chamado ANTES de get_message_stats."""
        src = self._stats_src()
        pos_check = src.find('_check_account_access')
        pos_service = src.find('get_message_stats')
        self.assertGreater(pos_check, -1, "Gate _check_account_access ausente em stats")
        self.assertGreater(pos_service, -1, "get_message_stats não encontrado no método")
        self.assertLess(
            pos_check,
            pos_service,
            "_check_account_access deve vir antes de get_message_stats",
        )

    def test_stats_nega_acesso_sem_permissao(self):
        """Usuário sem acesso à conta recebe PermissionDenied em stats."""
        from apps.whatsapp.api.views import MessageViewSet

        viewset = MessageViewSet()
        mock_user = MagicMock()
        mock_user.is_superuser = False

        mock_request = MagicMock()
        mock_request.user = mock_user
        viewset.request = mock_request
        viewset.format_kwarg = None

        victim_account_id = '22222222-0000-0000-0000-000000000002'
        validated = {
            'account_id': victim_account_id,
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
        }

        with patch('apps.whatsapp.api.views.MessageStatsSerializer') as MockSer, \
             patch('apps.whatsapp.api.views.accessible_whatsapp_account_ids',
                   return_value=[]) as mock_gate, \
             patch('apps.whatsapp.api.views.MessageService') as MockMsgSvc:
            MockSer.return_value.is_valid = lambda raise_exception=False: True
            MockSer.return_value.validated_data = validated
            MockMsgSvc.return_value.get_message_stats.return_value = {}

            with self.assertRaises(PermissionDenied):
                viewset.stats(mock_request)

            mock_gate.assert_called_once_with(mock_user)


@override_settings(
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class EmbeddedSignupStrExcTest(SimpleTestCase):
    """embedded_signup não deve retornar str(exc) em Exception genérica."""

    def _embedded_signup_src(self):
        from apps.whatsapp.api.views import WhatsAppAccountViewSet
        return inspect.getsource(WhatsAppAccountViewSet.embedded_signup)

    def test_sem_f_string_exc_no_502(self):
        """A resposta 502 não deve conter {exc} interpolado."""
        src = self._embedded_signup_src()
        # Verifica que não há f-string com {exc} dentro de qualquer resposta de erro genérica
        self.assertNotIn(
            "f'Falha no onboarding: {exc}'",
            src,
            "embedded_signup ainda expõe str(exc) na resposta 502 — "
            "tokens OAuth do Meta podem vazar.",
        )
        self.assertNotIn(
            'f"Falha no onboarding: {exc}"',
            src,
            "embedded_signup ainda expõe str(exc) na resposta 502 — "
            "tokens OAuth do Meta podem vazar.",
        )

    def test_mock_excecao_generica_retorna_mensagem_sem_detalhe(self):
        """Exceção genérica durante onboarding: resposta 502 sem mensagem interna."""
        from apps.whatsapp.api.views import WhatsAppAccountViewSet

        viewset = WhatsAppAccountViewSet()
        mock_request = MagicMock()
        mock_request.user = MagicMock(is_superuser=True)
        mock_request.data = {
            'code': 'fake-code',
            'waba_id': 'fake-waba',
            'phone_number_id': 'fake-pnid',
        }
        viewset.request = mock_request
        viewset.format_kwarg = None

        oauth_token = 'Bearer EAABsbCS_TOKEN_SECRETO_META_OAUTH'

        # EmbeddedSignupService é importado dentro do método (lazy), então
        # patchamos no módulo fonte.
        with patch(
            'apps.whatsapp.services.embedded_signup_service.EmbeddedSignupService'
        ) as MockSvc:
            MockSvc.return_value.onboard.side_effect = RuntimeError(oauth_token)

            response = viewset.embedded_signup(mock_request)

        self.assertEqual(response.status_code, 502)
        self.assertNotIn(
            oauth_token,
            str(response.data),
            "Token OAuth do Meta vazou na resposta 502 do embedded_signup",
        )
