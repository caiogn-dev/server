"""
Regressão de segurança: str(e) em exceções genéricas de views WhatsApp.

Garante que erros internos (mensagens de ORM, tokens de API do Meta) não
vazem para o corpo da resposta HTTP — apenas mensagens genéricas em pt-BR.

Cobre:
  - force_delete (500)
  - business_profile (502) — alto risco: resposta WA API pode conter tokens
  - sync_templates (502) — mesmo risco
"""
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings


@override_settings(
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class WhatsAppViewsStrELeakTest(SimpleTestCase):
    """Análise estática confirma que str(e) foi removido das respostas."""

    def _get_view_source(self):
        import inspect
        import apps.whatsapp.api.views as mod
        return inspect.getsource(mod)

    def test_force_delete_nao_retorna_str_e(self):
        """force_delete não expõe str(e) na resposta."""
        source = self._get_view_source()
        # Localiza o bloco except do force_delete (após 'Force deleted WhatsApp account')
        # e confirma que não há str(e) nele
        lines = source.splitlines()
        in_force_delete = False
        for i, line in enumerate(lines):
            if 'Error force deleting account' in line:
                in_force_delete = True
            if in_force_delete and 'return Response' in line:
                # Verifica as próximas 3 linhas pelo str(e)
                block = '\n'.join(lines[i:i+5])
                self.assertNotIn("str(e)", block,
                    "force_delete ainda expõe str(e) na resposta HTTP")
                break

    def test_business_profile_nao_retorna_str_e(self):
        """business_profile não expõe str(e) (protege tokens WA API)."""
        source = self._get_view_source()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'Error fetching business profile' in line:
                block = '\n'.join(lines[i:i+6])
                self.assertNotIn("str(e)", block,
                    "business_profile ainda expõe str(e) na resposta HTTP")
                break
        else:
            # A mensagem de log é a âncora de que o fix existe
            self.assertIn('Error fetching business profile', source,
                "Log de erro do business_profile não encontrado — fix pode ter sido revertido")

    def test_sync_templates_nao_retorna_str_e(self):
        """sync_templates não expõe str(e) (protege tokens WA API)."""
        source = self._get_view_source()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if 'Error syncing templates' in line:
                block = '\n'.join(lines[i:i+6])
                self.assertNotIn("str(e)", block,
                    "sync_templates ainda expõe str(e) na resposta HTTP")
                break
        else:
            self.assertIn('Error syncing templates', source,
                "Log de erro do sync_templates não encontrado — fix pode ter sido revertido")

    def test_mensagens_de_erro_sao_genericas_pt_br(self):
        """Respostas de erro usam mensagens genéricas em pt-BR."""
        source = self._get_view_source()
        self.assertIn('Erro interno ao excluir conta WhatsApp', source)
        self.assertIn('Erro ao obter perfil de negócio via API WhatsApp', source)
        self.assertIn('Erro ao sincronizar templates via API WhatsApp', source)

    def test_business_profile_mock_exception_retorna_502_sem_detalhe(self):
        """Simula exceção no WhatsAppAPIService — resposta deve ser genérica."""
        from apps.whatsapp.api.views import WhatsAppAccountViewSet
        from rest_framework.request import Request
        from unittest.mock import MagicMock

        viewset = WhatsAppAccountViewSet()
        mock_request = MagicMock()
        mock_request.user = MagicMock()

        mock_account = MagicMock()
        mock_account.id = 'test-account-id'

        secret_error = "AccessToken: EAABsbCS... (token secreto do Meta)"

        with patch.object(viewset, 'get_object', return_value=mock_account):
            with patch('apps.whatsapp.api.views.WhatsAppAPIService') as mock_svc_cls:
                mock_svc = MagicMock()
                mock_svc.get_business_profile.side_effect = Exception(secret_error)
                mock_svc_cls.return_value = mock_svc

                viewset.request = mock_request
                viewset.format_kwarg = None

                response = viewset.business_profile(mock_request, pk=None)

        self.assertEqual(response.status_code, 502)
        body = response.data
        self.assertNotIn('token', str(body).lower(),
            "Token secreto vazou na resposta HTTP do business_profile")
        self.assertNotIn(secret_error, str(body),
            "Mensagem de exceção interna vazou na resposta HTTP")
        self.assertIn('error', body)

    def test_sync_templates_mock_exception_retorna_502_sem_detalhe(self):
        """Simula exceção no sync_templates — resposta deve ser genérica."""
        from apps.whatsapp.api.views import WhatsAppAccountViewSet
        from unittest.mock import MagicMock

        viewset = WhatsAppAccountViewSet()
        mock_request = MagicMock()
        mock_request.user = MagicMock()

        mock_account = MagicMock()
        mock_account.id = 'test-account-id'

        secret_error = "Bearer EAABsbCS...XYZ Token Meta (secreto)"

        with patch.object(viewset, 'get_object', return_value=mock_account):
            with patch('apps.whatsapp.api.views.WhatsAppAPIService') as mock_svc_cls:
                mock_svc = MagicMock()
                mock_svc.get_templates.side_effect = Exception(secret_error)
                mock_svc_cls.return_value = mock_svc

                viewset.request = mock_request
                viewset.format_kwarg = None

                response = viewset.sync_templates(mock_request, pk=None)

        self.assertEqual(response.status_code, 502)
        body = response.data
        self.assertNotIn(secret_error, str(body),
            "Mensagem interna com token vazou na resposta HTTP do sync_templates")
        self.assertIn('error', body)
