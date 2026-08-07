"""Regressão de segurança: info-disclosure via str(e) em envio de campanha e e-mail [P2].

Antes do fix:
- EmailCampaignViewSet.send: except Exception → Response({'error': str(e)}, 500)
  — uma exceção de DB/Celery/conexão expõe mensagem interna ao requisitante autenticado.
- EmailMarketingService.send_single_email: return {'success': False, 'error': str(e)}
  — Resend API errors (URL interna, token, response body) propagam ao chamador.
- EmailAutomationService._send_automation_email: return {'success': False, 'error': str(e)}
  — mesmo padrão; pode chegar a views de automação.

Fix: mensagens genéricas em pt-BR; str(e) preservado apenas no logger.

Técnica: SimpleTestCase + análise estática + mocks de exceção. Sem DB/Docker.
"""
import importlib
import inspect
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, override_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_views():
    return importlib.import_module('apps.marketing.api.views')


def _load_email_service():
    return importlib.import_module('apps.marketing.services.email_marketing_service')


def _load_automation_service():
    return importlib.import_module('apps.marketing.services.email_automation_service')


_INTERNAL_ERROR_MSG = 'Connection refused: resend.io:443/api/emails — token=re_Abc123'


# ---------------------------------------------------------------------------
# 1. Análise estática — str(e) removido dos retornos HTTP
# ---------------------------------------------------------------------------

class TestViewSendNoStrE(SimpleTestCase):
    """A action send do EmailCampaignViewSet não deve retornar str(e) em exceções."""

    def test_send_action_except_block_no_str_e(self):
        src = inspect.getsource(_load_views())
        # Localiza o bloco do método send (action detail=True)
        # Busca: 'error': str(e) dentro de um return Response em qualquer view de campanha
        # O fix substitui str(e) por uma string literal genérica.
        import re
        # Não deve existir `'error': str(e)` em nenhum return Response das views
        matches = re.findall(r"return Response\(.*?str\(e\).*?\)", src, re.DOTALL)
        self.assertEqual(
            len(matches), 0,
            f"views.py não deve retornar str(e) em Response. Encontrado: {matches}"
        )


class TestEmailServiceNoStrEInReturn(SimpleTestCase):
    """send_single_email não deve retornar str(e) no dict de falha."""

    def test_send_single_email_no_str_e_in_return_dict(self):
        src = inspect.getsource(_load_email_service())
        import re
        # Procura retornos do tipo {'success': False, 'error': str(e)} em send_single_email
        # Extrai o corpo da função send_single_email
        match = re.search(
            r"def send_single_email\(.*?\n(?=    def |\Z)",
            src, re.DOTALL,
        )
        if match:
            fn_src = match.group(0)
            self.assertNotIn(
                "str(e)",
                fn_src,
                "send_single_email não deve incluir str(e) em nenhum return dict.",
            )

    def test_send_single_email_still_logs_error(self):
        """O erro real deve ser preservado nos logs internos."""
        src = inspect.getsource(_load_email_service())
        import re
        match = re.search(
            r"def send_single_email\(.*?\n(?=    def |\Z)",
            src, re.DOTALL,
        )
        if match:
            fn_src = match.group(0)
            self.assertTrue(
                'logger.error' in fn_src or 'logger.exception' in fn_src or 'logger.warning' in fn_src,
                "send_single_email deve logar o erro interno antes de retornar mensagem genérica.",
            )


class TestAutomationServiceNoStrEInReturn(SimpleTestCase):
    """_send_automation_email não deve retornar str(e) no dict de falha."""

    def test_automation_except_block_no_str_e_in_return(self):
        """str(e) pode existir em log.error_message (interno) mas NÃO em return dict."""
        src = inspect.getsource(_load_automation_service())
        import re
        # Verifica que nenhum return com 'error': str(e) existe no módulo inteiro
        # (str(e) em atribuições como log.error_message = str(e) é aceitável)
        return_str_e = re.findall(r"return \{[^}]*'error':\s*str\(e\)[^}]*\}", src)
        self.assertEqual(
            len(return_str_e), 0,
            "_send_automation_email não deve incluir 'error': str(e) em return dict. "
            f"Encontrado: {return_str_e}",
        )


# ---------------------------------------------------------------------------
# 2. Funcional — mock de exceção não expõe mensagem interna
# ---------------------------------------------------------------------------

_SETTINGS = dict(
    INSTALLED_APPS=[
        'django.contrib.contenttypes',
        'django.contrib.auth',
    ],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': (),
        'DEFAULT_PERMISSION_CLASSES': (),
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
    DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
)


class TestSendSingleEmailExceptionHidesDetails(SimpleTestCase):
    """send_single_email expondo exceção retorna mensagem genérica, não str(e)."""

    @override_settings(**_SETTINGS)
    def test_resend_exception_not_in_return(self):
        m = _load_email_service()

        # Injeta o mock diretamente no namespace do módulo — garante que a referência
        # local `resend` usada por send_single_email() aponte para o mock,
        # independentemente de o pacote real estar ou não instalado.
        resend_mock = MagicMock()
        resend_mock.Emails.send.side_effect = Exception(_INTERNAL_ERROR_MSG)

        service = m.EmailMarketingService.__new__(m.EmailMarketingService)
        service.enabled = True
        service.api_key = 'test_key'
        service.default_from_email = 'test@example.com'
        service.default_from_name = 'Test'

        with patch.dict(vars(m), {'resend': resend_mock}):
            result = service.send_single_email(
                to_email='customer@example.com',
                subject='Test',
                html_content='<p>Hello</p>',
            )

        self.assertFalse(result['success'])
        self.assertNotIn(_INTERNAL_ERROR_MSG, str(result.get('error', '')),
                         "Mensagem de erro interna do Resend não deve vazar na resposta.")
        self.assertNotIn('resend.io', str(result.get('error', '')))
        self.assertNotIn('token=', str(result.get('error', '')))


class TestEmailAutomationExceptionHidesDetails(SimpleTestCase):
    """_send_automation_email expondo exceção retorna mensagem genérica."""

    @override_settings(**_SETTINGS)
    def test_exception_not_in_return_dict(self):
        m = _load_automation_service()
        service = m.EmailAutomationService.__new__(m.EmailAutomationService)

        # log mock (evita acesso a DB)
        log_mock = MagicMock()
        log_mock.recipient_email = 'c@ex.com'
        log_mock.save = MagicMock()

        automation_mock = MagicMock()
        automation_mock.trigger_type = 'welcome'

        # Faz send_single_email levantar exceção com detalhe interno
        email_service_mock = MagicMock()
        email_service_mock.send_single_email.side_effect = Exception(_INTERNAL_ERROR_MSG)
        service.email_service = email_service_mock

        result = service._send_automation_email(automation_mock, log_mock, {})

        self.assertFalse(result['success'])
        self.assertNotIn(_INTERNAL_ERROR_MSG, str(result.get('error', '')),
                         "Detalhe interno não deve vazar no retorno da automação.")
