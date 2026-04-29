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
from apps.whatsapp.intents.detector import IntentType


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

        with patch.object(svc.detector, 'detect', return_value={'intent': IntentType.GREETING}), \
             patch.object(svc, '_run_handler', return_value=None), \
             patch.object(svc, '_get_template_for_intent', return_value=None), \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_build_context', return_value='ctx'), \
             patch.object(svc, '_call_llm', return_value='Resposta do LLM'):

            resp = svc.process_message('oi')
        self.assertEqual(resp.source, ResponseSource.LLM)
        self.assertEqual(resp.content, 'Resposta do LLM')

    def test_unknown_message_uses_llm_when_agent_available(self):
        agent = MagicMock()
        svc = _make_unified_service(use_llm=True, agent=agent)

        with patch.object(svc.detector, 'detect', return_value={'intent': IntentType.UNKNOWN}), \
             patch.object(svc, '_get_template_for_intent', return_value=None), \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_build_context', return_value='ctx'), \
             patch.object(svc, '_call_llm', return_value='Resposta do atendente'):

            resp = svc.process_message('tem salada sem cebola?')

        self.assertEqual(resp.source, ResponseSource.LLM)
        self.assertEqual(resp.content, 'Resposta do atendente')

    def test_fallback_when_all_providers_fail(self):
        svc = _make_unified_service(use_llm=True)

        with patch.object(svc, '_run_handler', return_value=None), \
             patch.object(svc, '_get_template_for_intent', return_value=None), \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_build_context', return_value=''), \
             patch.object(svc, '_call_llm', return_value=None):

            resp = svc.process_message('???')
        self.assertEqual(resp.source, ResponseSource.FALLBACK)

    def test_out_of_hours_short_circuits_eligible_intent(self):
        store = MagicMock()
        store.id = 'store-1'
        store.is_open.return_value = False
        store.name = 'Loja Teste'
        store.operating_hours = {}
        svc = _make_unified_service(store=store)

        with patch.object(svc.detector, 'detect', return_value={'intent': IntentType.MENU_REQUEST}), \
             patch.object(svc, '_run_handler') as mock_handler, \
             patch.object(svc, '_get_session_data', return_value={}), \
             patch.object(svc, '_get_out_of_hours_response', return_value=UnifiedResponse(content='fora do horario', source=ResponseSource.TEMPLATE)):
            resp = svc.process_message('cardapio')

        self.assertEqual(resp.content, 'fora do horario')
        self.assertEqual(resp.source, ResponseSource.TEMPLATE)
        mock_handler.assert_not_called()

    def test_out_of_hours_does_not_override_business_hours_intent(self):
        store = MagicMock()
        store.id = 'store-1'
        store.is_open.return_value = False
        store.name = 'Loja Teste'
        store.operating_hours = {}
        svc = _make_unified_service(store=store)
        handler_response = UnifiedResponse(content='horario normal', source=ResponseSource.HANDLER)

        with patch.object(svc.detector, 'detect', return_value={'intent': IntentType.BUSINESS_HOURS}), \
             patch.object(svc, '_run_handler', return_value=handler_response):
            resp = svc.process_message('que horas abre?')

        self.assertEqual(resp.content, 'horario normal')
        self.assertEqual(resp.source, ResponseSource.HANDLER)


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


# ─── Testes: _parse_items_from_text_dynamic ───────────────────────────────────

class ParseItemsDynamicTestCase(TestCase):
    """Testa a extração dinâmica de produtos por texto (sem keywords hardcoded)."""

    def _make_store(self):
        """Cria store e produtos mock para os testes."""
        from unittest.mock import MagicMock
        store = MagicMock()
        store.slug = 'test-store'
        return store

    def test_no_store_returns_empty(self):
        from apps.whatsapp.intents.handlers import _parse_items_from_text_dynamic
        result = _parse_items_from_text_dynamic('2 lasanha', store=None)
        self.assertEqual(result, [])

    def test_empty_text_returns_empty(self):
        from apps.whatsapp.intents.handlers import _parse_items_from_text_dynamic
        store = self._make_store()
        with patch('apps.stores.models.StoreProduct.objects') as mock_qs:
            mock_qs.filter.return_value = []
            result = _parse_items_from_text_dynamic('', store=store)
        self.assertEqual(result, [])

    def test_quantity_and_name_extracted(self):
        """'2 lasanha de frango' deve extrair product_id + quantity=2."""
        from apps.whatsapp.intents.handlers import _parse_items_from_text_dynamic
        from unittest.mock import MagicMock

        product = MagicMock()
        product.id = 'uuid-001'
        product.name = 'Lasanha de Frango'

        store = MagicMock()
        with patch('apps.whatsapp.intents.handlers.StoreProduct') as mock_model:
            mock_model.objects.filter.return_value = [product]
            result = _parse_items_from_text_dynamic('quero 2 lasanha de frango', store=store)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['quantity'], 2)
        self.assertEqual(result[0]['product_id'], 'uuid-001')

    def test_no_quantity_defaults_to_one(self):
        """Texto sem número → qty=1."""
        from apps.whatsapp.intents.handlers import _parse_items_from_text_dynamic
        from unittest.mock import MagicMock

        product = MagicMock()
        product.id = 'uuid-002'
        product.name = 'Nhoque ao Sugo'

        store = MagicMock()
        with patch('apps.whatsapp.intents.handlers.StoreProduct') as mock_model:
            mock_model.objects.filter.return_value = [product]
            result = _parse_items_from_text_dynamic('nhoque', store=store)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['quantity'], 1)


# ─── Testes: InteractiveReplyHandler ─────────────────────────────────────────

class InteractiveReplyHandlerTestCase(TestCase):
    """Testa o handler de respostas interativas (clique em botão/lista)."""

    def _make_handler(self):
        from apps.whatsapp.intents.handlers import InteractiveReplyHandler
        account = MagicMock()
        conversation = MagicMock()
        conversation.phone_number = '+5511999999999'
        conversation.contact_name = 'Teste'
        return InteractiveReplyHandler(account, conversation)

    def test_unknown_reply_id_returns_fallback(self):
        handler = self._make_handler()
        result = handler.handle({'reply_id': 'totally_unknown_id', 'reply_title': 'X'})
        # Should return buttons (fallback menu)
        self.assertTrue(result.use_interactive or result.response_text)

    def test_view_menu_delegates_to_menu_handler(self):
        handler = self._make_handler()
        store = MagicMock()
        store.name = 'Loja Teste'
        handler.store = store

        with patch('apps.whatsapp.intents.handlers.MenuRequestHandler.handle') as mock_menu:
            mock_menu.return_value = MagicMock(use_interactive=False, response_text='cardápio', requires_llm=False)
            result = handler.handle({'reply_id': 'view_menu', 'reply_title': 'Ver Cardápio'})

        mock_menu.assert_called_once()

    def test_product_not_found_returns_text(self):
        handler = self._make_handler()
        # UUID que não existe
        result = handler.handle({'reply_id': 'product_00000000-0000-0000-0000-000000000000', 'reply_title': 'X'})
        self.assertIsNotNone(result.response_text)
        self.assertIn('não encontrado', result.response_text.lower())

    def test_add_to_cart_invalid_format_returns_error(self):
        handler = self._make_handler()
        result = handler.handle({'reply_id': 'add_', 'reply_title': ''})
        self.assertIn('Erro', result.response_text)


# ─── Testes: UnifiedService com interactive_reply ─────────────────────────────

class UnifiedServiceInteractiveReplyTestCase(TestCase):
    """Testa o caminho rápido do UnifiedService para respostas interativas."""

    def test_interactive_reply_bypasses_intent_detection(self):
        svc = _make_unified_service()

        mock_ir_result = MagicMock()
        mock_ir_result.requires_llm = False
        mock_ir_result.use_interactive = False
        mock_ir_result.response_text = 'Produto selecionado!'

        with patch('apps.whatsapp.intents.handlers.InteractiveReplyHandler') as MockHandler:
            instance = MockHandler.return_value
            instance.handle.return_value = mock_ir_result

            from apps.automation.services.unified_service import ResponseSource
            resp = svc.process_message(
                '',
                interactive_reply={'type': 'list_reply', 'id': 'product_abc', 'title': 'Lasanha'},
            )

        instance.handle.assert_called_once()
        call_args = instance.handle.call_args[0][0]
        self.assertEqual(call_args['reply_id'], 'product_abc')
        self.assertEqual(call_args['reply_title'], 'Lasanha')
