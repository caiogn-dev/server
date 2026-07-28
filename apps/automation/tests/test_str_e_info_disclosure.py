"""
Regressão de segurança: str(e) em exceções genéricas de views de automação.

Cobre:
  - UnifiedProcessView (unified_views.py) — Exception → str(e) removido
  - AutoMessageViewSet.test_send (auto_message_views.py) — Exception → str(e) removido
  - AutoMessageViewSet.bulk_update (auto_message_views.py) — Exception → str(e) removido

Testes de análise estática rodam sem langchain.
Testes funcionais (mock) são skipped se langchain_core estiver ausente no ambiente.
"""
import unittest
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase

try:
    import langchain_core  # noqa: F401
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


class UnifiedViewStrELeakTest(SimpleTestCase):

    def _get_unified_source(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '../api/views/unified_views.py')
        path = os.path.abspath(path)
        with open(path) as f:
            return f.read()

    def test_unified_process_nao_retorna_str_e(self):
        """UnifiedProcessView não expõe str(e) na resposta de erro."""
        source = self._get_unified_source()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if '[UnifiedAPI] Error processing message' in line:
                block = '\n'.join(lines[i:i+8])
                self.assertNotIn("str(e)", block,
                    "UnifiedProcessView ainda expõe str(e) na resposta HTTP")
                return
        self.fail("Log '[UnifiedAPI] Error processing message' não encontrado — fix pode ter sido revertido")

    def test_unified_process_mensagem_generica(self):
        """Resposta de erro usa mensagem genérica sem detalhe interno."""
        source = self._get_unified_source()
        self.assertIn("'Erro ao processar mensagem.'", source,
            "Mensagem genérica 'Erro ao processar mensagem.' não encontrada — str(e) pode ter voltado")

    @unittest.skipUnless(HAS_LANGCHAIN, "langchain_core ausente no ambiente de CI mínimo")
    def test_unified_process_mock_exception_sem_detalhe(self):
        """Simula exceção interna — body da resposta deve ser genérico."""
        from apps.automation.api.views.unified_views import UnifiedProcessView

        view = UnifiedProcessView()
        mock_request = MagicMock()
        mock_request.user = MagicMock()
        mock_request.user.is_superuser = True
        # phone_number é obrigatório — sem ele a view devolve 400 antes de
        # chegar no caminho de exceção que este teste cobre.
        mock_request.data = {
            'account_id': 'test-acc',
            'phone_number': '5563999990000',
            'message': 'oi',
        }

        internal_error = "LLM API error: api_key=sk-secret-key-12345 (dado sensível)"

        with patch('apps.automation.api.views.unified_views.WhatsAppAccount') as mock_wa, \
                patch('apps.automation.api.views.unified_views.Conversation') as mock_conv, \
                patch('apps.automation.api.views.unified_views.LLMOrchestratorService') as mock_svc:
            qs = MagicMock()
            qs.filter.return_value = qs
            qs.distinct.return_value = qs
            qs.get.return_value = MagicMock()
            mock_wa.objects.filter.return_value = qs
            mock_wa.DoesNotExist = type('DoesNotExist', (Exception,), {})
            mock_conv.objects.get_or_create.return_value = (MagicMock(), True)
            # exceção interna com segredo estoura dentro do orquestrador LLM
            mock_svc.side_effect = Exception(internal_error)
            response = view.post(mock_request)

        self.assertEqual(response.status_code, 500)
        body = response.data
        self.assertNotIn(internal_error, str(body),
            "Dado sensível interno vazou na resposta HTTP do UnifiedProcessView")
        self.assertIn('error', body)
        self.assertNotIn('sk-secret', str(body))


class AutoMessageViewStrELeakTest(SimpleTestCase):

    def _get_auto_message_source(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '../api/views/auto_message_views.py')
        path = os.path.abspath(path)
        with open(path) as f:
            return f.read()

    def test_test_send_nao_retorna_str_e(self):
        """test_send não expõe str(e) na resposta de erro."""
        source = self._get_auto_message_source()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'Error sending test auto message' in line:
                block = '\n'.join(lines[i:i+8])
                self.assertNotIn("str(e)", block,
                    "test_send ainda expõe str(e) na resposta HTTP")
                return
        self.fail("Log 'Error sending test auto message' não encontrado — fix revertido?")

    def test_test_send_mensagem_generica(self):
        """Resposta do test_send usa mensagem genérica em pt-BR."""
        source = self._get_auto_message_source()
        self.assertIn("'Erro ao enviar mensagem de teste.'", source,
            "Mensagem genérica do test_send não encontrada — str(e) pode ter voltado")

    def test_bulk_update_nao_retorna_str_e_nos_erros(self):
        """bulk_update não expõe str(e) na lista de erros."""
        source = self._get_auto_message_source()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'Error updating auto message' in line:
                block = '\n'.join(lines[i:i+4])
                self.assertNotIn("str(e)", block,
                    "bulk_update ainda expõe str(e) na lista de erros da resposta HTTP")
                return
        self.fail("Log 'Error updating auto message' não encontrado — fix revertido?")

    def test_bulk_update_mensagem_generica(self):
        """bulk_update acumula mensagens genéricas na lista de erros."""
        source = self._get_auto_message_source()
        self.assertIn("Erro ao atualizar mensagem", source,
            "Mensagem genérica do bulk_update não encontrada")

    @unittest.skipUnless(HAS_LANGCHAIN, "langchain_core ausente no ambiente de CI mínimo")
    def test_bulk_update_mock_exception_sem_detalhe(self):
        """bulk_update com exceção interna retorna erro genérico na lista."""
        from apps.automation.api.views.auto_message_views import AutoMessageViewSet
        from django.db import DatabaseError

        viewset = AutoMessageViewSet()
        mock_request = MagicMock()
        mock_request.user = MagicMock()
        internal_msg = "column auto_message.secret_field does not exist (ORM leak)"
        mock_request.data = {'updates': [{'id': 'msg-123', 'is_active': True}]}

        mock_qs = MagicMock()
        mock_qs.get.side_effect = DatabaseError(internal_msg)

        with patch.object(viewset, 'get_queryset', return_value=mock_qs):
            viewset.request = mock_request
            viewset.format_kwarg = None
            response = viewset.bulk_update(mock_request)

        self.assertEqual(response.status_code, 200)
        errors = response.data.get('errors', [])
        self.assertTrue(len(errors) > 0, "Nenhum erro registrado na lista")
        self.assertNotIn(internal_msg, str(errors),
            "Mensagem interna de DB vazou na lista de erros do bulk_update")
        self.assertIn('msg-123', errors[0])
        self.assertNotIn('column', errors[0])
