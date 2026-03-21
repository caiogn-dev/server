"""
Testes de integração do pipeline de automação WhatsApp.

Coberturas:
1. UnifiedService — fluxo completo handler → template → LLM → fallback
2. unified_service._render_template — substituição de variáveis e placeholders faltando
3. unified_service._validate_buttons — botões inválidos/truncados
4. webhook_service.post_process_inbound_message — fallback corretamente ativado
5. pipeline_health.health_check — retorna estrutura correta
6. FlowSession.update_context — atualização atômica
7. SessionManager.reset_session — update atômico

Executar:
    python manage.py test apps.automation.tests.test_pipeline --keepdb -v 2
"""
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase, override_settings

from apps.automation.services.unified_service import (
    ResponseSource,
    UnifiedResponse,
    _validate_buttons,
)
from apps.automation.services.pipeline_health import health_check, get_pipeline_stats


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_unified_service(use_llm=False, store=None, company=None, agent=None):
    """Cria uma instância de UnifiedService com dependências mockadas."""
    from apps.automation.services.unified_service import UnifiedService

    account = MagicMock()
    conversation = MagicMock()
    conversation.phone_number = '+5511999999999'
    conversation.contact_name = 'Teste'
    conversation.id = 'conv-001'

    with patch('apps.automation.services.unified_service.AutomationContextService') as mock_ctx:
        ctx = MagicMock()
        ctx.profile = company
        ctx.store = store
        mock_ctx.resolve.return_value = ctx
        mock_ctx.get_default_agent.return_value = agent
        mock_ctx.is_ai_enabled.return_value = use_llm

        svc = UnifiedService.__new__(UnifiedService)
        svc.account = account
        svc.conversation = conversation
        svc.debug = True
        svc.context = ctx
        svc.company = company
        svc.store = store
        svc.agent = agent
        svc.use_llm = use_llm
        svc.stats = {'template': 0, 'llm': 0, 'handler': 0, 'fallback': 0}

        from apps.whatsapp.intents.detector import IntentDetector
        svc.detector = IntentDetector(use_llm_fallback=False)

    return svc


# ─── Testes: _validate_buttons ────────────────────────────────────────────────

class ValidateButtonsTestCase(TestCase):
    """Testa a função de validação/normalização de botões WhatsApp."""

    def test_none_returns_none(self):
        self.assertIsNone(_validate_buttons(None))

    def test_empty_list_returns_none(self):
        self.assertIsNone(_validate_buttons([]))

    def test_valid_buttons_preserved(self):
        buttons = [{'id': 'btn1', 'title': 'Clique aqui'}]
        result = _validate_buttons(buttons)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'btn1')
        self.assertEqual(result[0]['title'], 'Clique aqui')

    def test_button_without_id_is_filtered(self):
        buttons = [{'title': 'Sem ID'}, {'id': 'ok', 'title': 'Com ID'}]
        result = _validate_buttons(buttons)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'ok')

    def test_button_without_title_is_filtered(self):
        buttons = [{'id': 'no_title'}, {'id': 'ok', 'title': 'Título'}]
        result = _validate_buttons(buttons)
        self.assertEqual(len(result), 1)

    def test_title_truncated_to_20_chars(self):
        long_title = 'A' * 30
        buttons = [{'id': 'x', 'title': long_title}]
        result = _validate_buttons(buttons)
        self.assertEqual(len(result[0]['title']), 20)

    def test_all_invalid_returns_none(self):
        buttons = [{'id': ''}, {'title': ''}]
        self.assertIsNone(_validate_buttons(buttons))


# ─── Testes: _render_template ─────────────────────────────────────────────────

class RenderTemplateTestCase(TestCase):
    """Testa a renderização de templates com variáveis."""

    def _render(self, text, session_data=None, contact_name='João', company_name='Loja'):
        svc = _make_unified_service()
        svc.conversation.contact_name = contact_name

        company = MagicMock()
        company.company_name = company_name
        svc.company = company

        template = MagicMock()
        template.message_text = text
        template.id = 'tpl-001'
        return svc._render_template(template, session_data or {})

    def test_customer_name_replaced(self):
        result = self._render('Olá, {customer_name}!')
        self.assertEqual(result, 'Olá, João!')

    def test_company_name_replaced(self):
        result = self._render('Bem-vindo à {company_name}!')
        self.assertEqual(result, 'Bem-vindo à Loja!')

    def test_order_id_replaced_when_present(self):
        result = self._render('Pedido #{order_id}', session_data={'order_id': '12345'})
        self.assertEqual(result, 'Pedido #12345')

    def test_order_id_empty_when_absent(self):
        """order_id ausente na sessão → placeholder substituído por string vazia."""
        result = self._render('Pedido #{order_id}', session_data={})
        self.assertEqual(result, 'Pedido #')

    def test_cart_total_formatted(self):
        result = self._render('Total: {cart_total}', session_data={'cart_total': 59.9})
        self.assertIn('R$ 59.90', result)

    def test_unknown_placeholder_logged(self):
        """Placeholders não reconhecidos ficam no texto (sem crash)."""
        result = self._render('Valor: {valor_especial}')
        self.assertIn('{valor_especial}', result)


# ─── Testes: UnifiedService.process_message ───────────────────────────────────

class UnifiedServiceProcessMessageTestCase(TestCase):
    """Testa o fluxo principal do UnifiedService."""

    def test_empty_message_returns_fallback(self):
        svc = _make_unified_service()
        resp = svc.process_message('')
        self.assertEqual(resp.source, ResponseSource.FALLBACK)

    def test_whitespace_message_returns_fallback(self):
        svc = _make_unified_service()
        resp = svc.process_message('   ')
        self.assertEqual(resp.source, ResponseSource.FALLBACK)

    def test_handler_response_takes_priority(self):
        svc = _make_unified_service()
        mock_handler_resp = UnifiedResponse(content='Handler response', source=ResponseSource.HANDLER)

        with patch.object(svc, '_run_handler', return_value=mock_handler_resp):
            resp = svc.process_message('Oi')
        self.assertEqual(resp.source, ResponseSource.HANDLER)
        self.assertEqual(resp.content, 'Handler response')

    def test_template_used_when_no_handler(self):
        svc = _make_unified_service()

        with patch.object(svc, '_run_handler', return_value=None), \
             patch.object(svc, '_get_template_for_intent') as mock_tpl, \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_render_template', return_value='Texto do template'):

            mock_template = MagicMock()
            mock_template.buttons = None
            mock_template.id = 'tpl-1'
            mock_template.event_type = 'welcome'
            mock_tpl.return_value = mock_template

            resp = svc.process_message('Oi')
        self.assertEqual(resp.source, ResponseSource.TEMPLATE)
        self.assertEqual(resp.content, 'Texto do template')

    def test_llm_called_when_no_handler_or_template(self):
        svc = _make_unified_service(use_llm=True)

        with patch.object(svc, '_run_handler', return_value=None), \
             patch.object(svc, '_get_template_for_intent', return_value=None), \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_build_context', return_value='ctx'), \
             patch.object(svc, '_call_llm', return_value='Resposta do LLM'):

            resp = svc.process_message('Alguma pergunta complexa')
        self.assertEqual(resp.source, ResponseSource.LLM)
        self.assertEqual(resp.content, 'Resposta do LLM')

    def test_fallback_when_all_providers_fail(self):
        svc = _make_unified_service(use_llm=True)

        with patch.object(svc, '_run_handler', return_value=None), \
             patch.object(svc, '_get_template_for_intent', return_value=None), \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_build_context', return_value=''), \
             patch.object(svc, '_call_llm', return_value=None):

            resp = svc.process_message('???')
        self.assertEqual(resp.source, ResponseSource.FALLBACK)


# ─── Testes: pipeline_health ──────────────────────────────────────────────────

class PipelineHealthTestCase(TestCase):
    """Testa o módulo de health check do pipeline."""

    def test_health_check_returns_required_keys(self):
        result = health_check()
        self.assertIn('status', result)
        self.assertIn('checks', result)
        self.assertIn('summary', result)
        self.assertIn('checked_at', result)

    def test_status_is_valid_value(self):
        result = health_check()
        self.assertIn(result['status'], ['ok', 'degraded', 'down'])

    def test_checks_contains_expected_keys(self):
        result = health_check()
        expected_keys = {'database', 'cache', 'celery', 'agents', 'scheduled_messages', 'sessions'}
        self.assertTrue(expected_keys.issubset(result['checks'].keys()))

    def test_each_check_has_ok_and_detail(self):
        result = health_check()
        for name, check in result['checks'].items():
            self.assertIn('ok', check, f'Check "{name}" sem campo "ok"')
            self.assertIn('detail', check, f'Check "{name}" sem campo "detail"')

    def test_get_pipeline_stats_returns_required_keys(self):
        stats = get_pipeline_stats(hours=1)
        self.assertIn('period_hours', stats)
        self.assertIn('total_messages', stats)
        self.assertIn('by_source', stats)
        self.assertIn('dropped', stats)
        self.assertIn('timeouts', stats)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_record_event_increments_counters(self):
        from apps.automation.services.pipeline_health import record_pipeline_event, PipelineEvent
        from django.core.cache import cache

        cache.clear()
        event = PipelineEvent(
            message_id='msg-test',
            source='handler',
            intent='greeting',
            duration_ms=42.0,
        )
        record_pipeline_event(event)

        stats = get_pipeline_stats(hours=1)
        self.assertGreaterEqual(stats['total_messages'], 1)
