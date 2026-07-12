"""Regressão de segurança — info-disclosure via str(e) em combo, subscription, print e webhook.

Cobre quatro pontos que expunham mensagens internas de exceção na resposta HTTP:

  1. AddComboToCartView (AllowAny) — StoreCartComboItem.objects.create falha →
     antes retornava {'detail': f'Erro ao adicionar combo ao carrinho: {str(e)}'}
     expondo erros do ORM/DB para qualquer usuário anônimo.

  2. StoreSubscribeView (IsAuthenticated) — SubscriptionError com mensagem interna
     (ex: 'Token MercadoPago não configurado.') → antes retornava str(e) para o dono da loja.

  3. StoreSubscriptionCancelView — mesmo vetor que (2).

  4. StoreSubscriptionChangePlanView — mesmo vetor que (2).

  5. MercadoPagoWebhookView — Exception no handler → antes retornava
     {'status': 'error', 'message': str(e)} para o Mercado Pago (disclosure para serviço externo).

  6. PrintJobSSEView (SSE stream) — Exception no generator → antes emitia
     {'type': 'error', 'message': str(e)} no stream para dashboards autenticados.

Todos os testes usam SimpleTestCase + mocks ou análise estática (sem banco, sem migrations).
"""
import ast
import json
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase, RequestFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(is_authenticated=True, is_superuser=False):
    u = Mock()
    u.is_authenticated = is_authenticated
    u.is_superuser = is_superuser
    u.id = 1
    u.email = 'test@example.com'
    return u


def _make_store(slug='test-store'):
    s = Mock()
    s.slug = slug
    return s


# ---------------------------------------------------------------------------
# 1. AddComboToCartView — análise estática garante que str(e) foi removido
# ---------------------------------------------------------------------------

class AddComboToCartStrELeakTest(SimpleTestCase):
    """Verifica via análise estática que o endpoint AllowAny não usa str(e) na resposta."""

    def _get_source(self):
        import apps.stores.api.views.combo_views as mod
        return open(mod.__file__).read()

    def test_str_e_not_in_except_response(self):
        """str(e) não pode aparecer como conteúdo de 'detail' no except de create."""
        source = self._get_source()
        # Garantia ampla: str(e) não aparece dentro de f-string que compõe 'detail'
        self.assertNotIn("f'Erro ao adicionar combo ao carrinho: {str(e)}'", source)
        self.assertNotIn('f"Erro ao adicionar combo ao carrinho: {str(e)}"', source)

    def test_generic_message_present(self):
        """Mensagem genérica de pt-BR está presente no except handler."""
        source = self._get_source()
        self.assertIn("'Erro ao adicionar combo ao carrinho.'", source)

    def test_logger_call_present(self):
        """O logger.error registra internamente o erro completo antes de retornar genérico."""
        source = self._get_source()
        self.assertIn('logger.error', source)

    def test_no_str_e_in_detail_value(self):
        """Nenhuma ocorrência de str(e) como valor de 'detail' em linhas de retorno."""
        source = self._get_source()
        for line in source.splitlines():
            if 'detail' in line and 'str(e)' in line:
                self.fail(
                    f"str(e) ainda presente em linha com 'detail' em combo_views.py: {line.strip()}"
                )


# ---------------------------------------------------------------------------
# 2–4. Subscription views — IsAuthenticated, mensagens internas do serviço
# ---------------------------------------------------------------------------

class SubscriptionStrELeakTest(SimpleTestCase):
    """Os endpoints de assinatura não devem expor SubscriptionError.str() ao cliente."""

    def test_create_subscription_error_hides_internal_message(self):
        from apps.stores.api.views.subscription_views import StoreSubscribeView
        from apps.stores.services.subscription_service import SubscriptionError

        internal_msg = 'Token MercadoPago não configurado.'
        view = StoreSubscribeView()
        request = Mock()
        request.user = _user()
        request.data = {'plan': 'starter'}

        with patch('apps.stores.api.views.subscription_views.get_object_or_404',
                   return_value=_make_store()), \
             patch('apps.stores.api.views.subscription_views._can_manage', return_value=True), \
             patch('apps.stores.api.views.subscription_views.subscription_service.create_subscription',
                   side_effect=SubscriptionError(internal_msg)):
            response = view.post(request, store_slug='test-store')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(internal_msg, str(response.data))

    def test_create_subscription_error_returns_generic_message(self):
        from apps.stores.api.views.subscription_views import StoreSubscribeView
        from apps.stores.services.subscription_service import SubscriptionError

        view = StoreSubscribeView()
        request = Mock()
        request.user = _user()
        request.data = {'plan': 'pro'}

        with patch('apps.stores.api.views.subscription_views.get_object_or_404',
                   return_value=_make_store()), \
             patch('apps.stores.api.views.subscription_views._can_manage', return_value=True), \
             patch('apps.stores.api.views.subscription_views.subscription_service.create_subscription',
                   side_effect=SubscriptionError('Token MercadoPago não configurado.')):
            response = view.post(request, store_slug='test-store')

        self.assertIn('Erro ao criar assinatura', str(response.data.get('detail', '')))

    def test_cancel_subscription_error_hides_internal_message(self):
        from apps.stores.api.views.subscription_views import StoreSubscriptionCancelView
        from apps.stores.services.subscription_service import SubscriptionError

        internal_msg = 'Loja isenta de cobrança (grandfather).'
        view = StoreSubscriptionCancelView()
        request = Mock()
        request.user = _user()
        request.data = {}

        with patch('apps.stores.api.views.subscription_views.get_object_or_404',
                   return_value=_make_store()), \
             patch('apps.stores.api.views.subscription_views._can_manage', return_value=True), \
             patch('apps.stores.api.views.subscription_views.subscription_service.cancel_subscription',
                   side_effect=SubscriptionError(internal_msg)):
            response = view.post(request, store_slug='test-store')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(internal_msg, str(response.data))
        self.assertIn('cancelar assinatura', str(response.data.get('detail', '')))

    def test_change_plan_error_hides_mp_status(self):
        from apps.stores.api.views.subscription_views import StoreSubscriptionChangePlanView
        from apps.stores.services.subscription_service import SubscriptionError

        mp_detail = 'MercadoPago recusou a assinatura: rejected'
        view = StoreSubscriptionChangePlanView()
        request = Mock()
        request.user = _user()
        request.data = {'plan': 'premium'}

        with patch('apps.stores.api.views.subscription_views.get_object_or_404',
                   return_value=_make_store()), \
             patch('apps.stores.api.views.subscription_views._can_manage', return_value=True), \
             patch('apps.stores.api.views.subscription_views.subscription_service.change_plan',
                   side_effect=SubscriptionError(mp_detail)):
            response = view.post(request, store_slug='test-store')

        self.assertEqual(response.status_code, 400)
        self.assertNotIn(mp_detail, str(response.data))
        self.assertNotIn('rejected', str(response.data))
        self.assertIn('plano', str(response.data.get('detail', '')).lower())

    def test_subscription_source_does_not_have_str_e(self):
        """Análise estática: nenhum str(e) exposto no corpo de resposta dos endpoints."""
        import apps.stores.api.views.subscription_views as mod
        source = open(mod.__file__).read()
        for line in source.splitlines():
            if 'return Response' in line and 'str(e)' in line:
                self.fail(
                    f"str(e) ainda em return Response em subscription_views.py: {line.strip()}"
                )


# ---------------------------------------------------------------------------
# 5. MercadoPagoWebhookView — análise estática garante que 'message': str(e) foi removido
# ---------------------------------------------------------------------------

class WebhookStrELeakTest(SimpleTestCase):
    """O handler de webhook não deve incluir str(e) na chave 'message' da resposta."""

    def _get_source(self):
        import importlib, sys
        # Importa diretamente o módulo de webhooks sem passar pelo __init__.py da api
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location(
            'apps.stores.api.webhooks_direct',
            os.path.join(os.path.dirname(__file__), '..', 'api', 'webhooks.py')
        )
        mod = importlib.util.module_from_spec(spec)
        return open(spec.origin).read()

    def test_webhook_response_does_not_have_message_str_e(self):
        """Nenhum 'message': str(e) deve existir no handler de webhook."""
        source = self._get_source()
        self.assertNotIn("'message': str(e)", source)
        self.assertNotIn('"message": str(e)', source)

    def test_webhook_status_error_without_message_key(self):
        """Resposta de erro do webhook contém apenas 'status' sem 'message'."""
        source = self._get_source()
        # A resposta de erro deve ter apenas status='error', sem message
        self.assertIn("'status': 'error'", source)
        # Confirma que a linha com status error não tem 'message' ao lado
        for line in source.splitlines():
            if "'status': 'error'" in line and "'message'" in line:
                self.fail(
                    f"Chave 'message' ainda presente na resposta de erro do webhook: {line.strip()}"
                )

    def test_webhook_logger_preserves_error(self):
        """O logger ainda registra o erro completo internamente."""
        source = self._get_source()
        self.assertIn('logger.error', source)


# ---------------------------------------------------------------------------
# 6. PrintJobSSEView — stream não deve emitir str(e)
# ---------------------------------------------------------------------------

class PrintViewSSEStrELeakTest(SimpleTestCase):
    """O SSE generator de print jobs não deve vazar str(e) nos eventos."""

    def _get_source(self):
        import apps.stores.api.views.print_views as mod
        return open(mod.__file__).read()

    def test_sse_error_event_does_not_contain_str_e(self):
        """Evento de erro no SSE usa mensagem genérica, não str(e)."""
        source = self._get_source()
        self.assertNotIn("'message': str(e)", source)
        self.assertNotIn('"message": str(e)', source)

    def test_sse_error_event_uses_generic_message(self):
        """A mensagem genérica está presente no handler de erro do SSE."""
        source = self._get_source()
        self.assertIn('Erro interno no servidor', source)

    def test_sse_yield_error_line_has_no_str_e(self):
        """Nenhum yield de erro no SSE pode conter str(e)."""
        source = self._get_source()
        for i, line in enumerate(source.splitlines(), 1):
            if 'yield' in line and 'error' in line and 'str(e)' in line:
                self.fail(
                    f"str(e) ainda presente no yield de erro em print_views.py linha {i}: {line.strip()}"
                )
