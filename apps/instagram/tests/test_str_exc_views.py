"""Regressão de segurança: str(exc) em exception handlers das views Instagram.

Vetores: 5 actions do InstagramAccountViewSet e InstagramMediaViewSet capturam
`except Exception as exc` e retornam `{"error": str(exc)}` ao cliente autenticado.
Se a InstagramAPI ou InstagramGraphService lançar uma exceção interna (ex: SSL, conexão,
OAuth) o erro real é exposto — podendo conter token, URL interna, host ou certificado.

Fix: substituir str(exc) por mensagem genérica; logar erro real internamente.
"""
import inspect
from django.test import SimpleTestCase


def _source(module_path):
    import importlib
    m = importlib.import_module(module_path)
    return inspect.getsource(m)


class InstagramViewsStrExcTest(SimpleTestCase):
    """Valida que nenhuma action genérica do Instagram retorna str(exc)."""

    def _get_source(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'api', 'views.py'
        )
        with open(os.path.abspath(path)) as f:
            return f.read()

    def test_refresh_token_nao_usa_str_exc(self):
        """refresh_page_token não expõe str(exc) ao cliente."""
        source = self._get_source()
        lines = source.splitlines()
        in_refresh = False
        for line in lines:
            if 'def refresh_page_token' in line:
                in_refresh = True
            if in_refresh and 'str(exc)' in line:
                self.fail(
                    "refresh_page_token retorna str(exc) — info-disclosure de "
                    "erros internos da Meta Graph API"
                )
            if in_refresh and 'def ' in line and 'refresh_page_token' not in line:
                break

    def test_account_insights_nao_usa_str_exc(self):
        """insights da conta não expõe str(exc) ao cliente."""
        source = self._get_source()
        lines = source.splitlines()
        in_insights = False
        count = 0
        for line in lines:
            if 'def insights' in line:
                count += 1
                if count == 1:  # primeira ocorrência: insights da conta
                    in_insights = True
            if in_insights and 'str(exc)' in line:
                self.fail(
                    "insights (conta) retorna str(exc) — info-disclosure"
                )
            if in_insights and 'def ' in line and 'def insights' not in line and count == 1:
                in_insights = False
                break

    def test_media_publish_nao_usa_str_exc(self):
        """publish de mídia não expõe str(exc) ao cliente."""
        source = self._get_source()
        lines = source.splitlines()
        in_publish = False
        for line in lines:
            if 'def publish' in line:
                in_publish = True
            if in_publish and 'str(exc)' in line:
                self.fail(
                    "publish retorna str(exc) — info-disclosure de erros de upload"
                )
            if in_publish and 'def ' in line and 'def publish' not in line:
                break

    def test_media_insights_nao_usa_str_exc(self):
        """insights de mídia não expõe str(exc) ao cliente."""
        source = self._get_source()
        # procura a segunda definição de 'def insights' (a de media)
        lines = source.splitlines()
        count = 0
        in_insights = False
        for line in lines:
            if 'def insights' in line:
                count += 1
                if count == 2:
                    in_insights = True
            if in_insights and 'str(exc)' in line:
                self.fail(
                    "insights (mídia) retorna str(exc) — info-disclosure"
                )
            if in_insights and 'def ' in line and 'def insights' not in line and count == 2:
                break

    def test_media_comments_nao_usa_str_exc(self):
        """comments de mídia não expõe str(exc) ao cliente."""
        source = self._get_source()
        lines = source.splitlines()
        in_comments = False
        for line in lines:
            if 'def comments' in line:
                in_comments = True
            if in_comments and 'str(exc)' in line:
                self.fail(
                    "comments retorna str(exc) — info-disclosure de erros de API"
                )
            if in_comments and 'def ' in line and 'def comments' not in line:
                break

    def test_logger_presente_nos_handlers(self):
        """Após o fix, cada handler deve logar o erro real antes de responder."""
        source = self._get_source()
        # Verificação genérica: o módulo deve usar logger (já existe)
        self.assertIn('logger', source)
        self.assertIn('logger.exception', source,
                      "Handlers devem usar logger.exception para registrar o erro real")


class MessagingViewsStrExcTest(SimpleTestCase):
    """Valida que views de Messenger não expõem str(exc)."""

    def _get_source(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'messaging', 'api', 'views.py'
        )
        with open(os.path.abspath(path)) as f:
            return f.read()

    def test_sync_nao_usa_str_exc(self):
        """MessengerAccountViewSet.sync não retorna str(exc)."""
        source = self._get_source()
        lines = source.splitlines()
        in_sync = False
        for line in lines:
            if 'def sync' in line:
                in_sync = True
            if in_sync and 'str(exc)' in line:
                self.fail(
                    "MessengerAccountViewSet.sync retorna str(exc) — "
                    "pode expor token/URL interna do Facebook Messenger"
                )
            if in_sync and 'def ' in line and 'def sync' not in line:
                break

    def test_send_message_nao_usa_str_exc(self):
        """MessengerConversationViewSet.send_message não retorna str(exc)."""
        source = self._get_source()
        lines = source.splitlines()
        in_send = False
        for line in lines:
            if 'def send_message' in line:
                in_send = True
            if in_send and 'str(exc)' in line:
                self.fail(
                    "send_message retorna str(exc) — pode expor erros internos do Messenger"
                )
            if in_send and 'def ' in line and 'def send_message' not in line:
                break


class WhatsAppEmbeddedSignupStrExcTest(SimpleTestCase):
    """Valida que embedded_signup não expõe exc interno ao cliente."""

    def _get_source(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'whatsapp', 'api', 'views.py'
        )
        with open(os.path.abspath(path)) as f:
            return f.read()

    def test_embedded_signup_nao_expoe_f_string_exc(self):
        """embedded_signup não usa f'...: {exc}' no Response de Exception genérica."""
        source = self._get_source()
        lines = source.splitlines()
        in_signup = False
        in_except_block = False
        for line in lines:
            stripped = line.strip()
            if 'def embedded_signup' in stripped:
                in_signup = True
            if in_signup and 'except Exception' in stripped:
                in_except_block = True
            if in_except_block:
                if ('{exc}' in stripped or 'str(exc)' in stripped) and 'Response' in stripped:
                    self.fail(
                        "embedded_signup expõe {exc}/str(exc) na resposta HTTP de "
                        "Exception genérica — pode vazar erro interno de conexão Meta"
                    )
            if in_signup and stripped.startswith('def ') and 'embedded_signup' not in stripped:
                break
