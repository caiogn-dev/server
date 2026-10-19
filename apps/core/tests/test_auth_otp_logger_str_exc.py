"""Regressão: OTP WhatsApp auth não deve expor detalhes de exceção nos logs.

Três pontos cobertos:

1. send_whatsapp_auth_code (views.py) — captura WhatsAppAuthError com
   `logger.error('... %s', e)`. O `%s % e` coloca `str(e)` no campo *message*
   do log record, que chega ao Sentry como texto livre sem possibilidade de
   scrubbing por campo.

2. resend_whatsapp_auth_code (views.py) — mesmo padrão na função de reenvio.

3. WhatsAppAuthService.send_auth_code (whatsapp_auth.py) — quando
   send_template_message falha, o handler captura 8 atributos do exception
   (str, repr, message, code, details, traceback completo) e os loga via
   logger.error(f"...") individualmente no campo message. Além disso, o
   init_error do MessageService é embutido via
   `logger.error(f"... {init_error}\\n{traceback.format_exc()}")`.

O padrão correto: logger.error sem interpolação do exception — apenas tipo
ou msg genérica, exc_info separado para Sentry/CloudWatch.

Todos SimpleTestCase — sem banco, sem rede.
Rodar:
  python3 -m unittest apps.core.tests.test_auth_otp_logger_str_exc -v
OU (com Django):
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
  python manage.py test apps.core.tests.test_auth_otp_logger_str_exc -v 2
"""
import inspect
import re
import unittest


def _src_views():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    # Lê o arquivo fonte diretamente para evitar importar o módulo Django inteiro
    import pathlib
    p = pathlib.Path(__file__).parent.parent.parent / 'core' / 'auth' / 'views.py'
    return p.read_text()


def _src_whatsapp_auth():
    import pathlib
    p = pathlib.Path(__file__).parent.parent.parent / 'core' / 'auth' / 'whatsapp_auth.py'
    return p.read_text()


class SendCodeViewLoggerTest(unittest.TestCase):
    """send_whatsapp_auth_code não deve interpolar exception no campo message."""

    def test_nao_usa_logger_error_com_excecao_interpolada(self):
        """logger.error('... %s', e) coloca str(e) no message — remover a variável."""
        src = _src_views()
        self.assertNotIn(
            "logger.error('[WHATSAPP AUTH API] Erro ao enviar código: %s', e)",
            src,
            "logger.error com '%s, e' expõe str(WhatsAppAuthError) no campo message do log",
        )

    def test_nao_interpola_excecao_como_argumento_de_formatacao(self):
        """Nenhum logger.error deve ter a exceção capturada como argumento de formatação."""
        src = _src_views()
        matches = re.findall(r"logger\.error\(['\"][^'\"]*['\"],\s*e\b", src)
        self.assertEqual(
            matches, [],
            f"logger.error com exception como argumento de formatação: {matches}",
        )


class ResendCodeViewLoggerTest(unittest.TestCase):
    """resend_whatsapp_auth_code não deve interpolar exception no campo message."""

    def test_nao_usa_logger_error_com_excecao_interpolada(self):
        """logger.error('... %s', e) coloca str(e) no message — remover a variável."""
        src = _src_views()
        self.assertNotIn(
            "logger.error('[WHATSAPP AUTH API] Erro ao reenviar código: %s', e)",
            src,
            "logger.error com '%s, e' expõe str(WhatsAppAuthError) no campo message do log",
        )


class SendAuthCodeLoggerTest(unittest.TestCase):
    """WhatsAppAuthService.send_auth_code não deve despejar exception no message."""

    def test_nao_usa_traceback_format_exc_em_logger_error(self):
        """`traceback.format_exc()` em f-string de logger.error coloca stack trace no message."""
        src = _src_whatsapp_auth()
        matches = re.findall(r'logger\.error\(f["\'].*traceback\.format_exc\(\)', src)
        self.assertEqual(
            matches, [],
            "logger.error com traceback.format_exc() no message — use logger.exception ou exc_info separado",
        )

    def test_nao_usa_init_error_em_logger_error(self):
        """`{init_error}` em f-string de logger.error coloca str(exc) no message."""
        src = _src_whatsapp_auth()
        matches = re.findall(r'logger\.error\(f["\'][^"\']*\{init_error\}', src)
        self.assertEqual(
            matches, [],
            "logger.error(f'...{init_error}...') expõe str(Exception) no campo message",
        )

    def test_nao_usa_error_str_em_logger_error(self):
        """`{error_str}` em f-string de logger.error coloca str(e) no message."""
        src = _src_whatsapp_auth()
        bad = [l.strip() for l in src.splitlines() if 'logger.error' in l and '{error_str}' in l]
        self.assertEqual(
            bad, [],
            f"logger.error com {{error_str}} no message: {bad}",
        )

    def test_nao_usa_error_repr_em_logger_error(self):
        """`{error_repr}` em f-string de logger.error coloca repr(e) no message."""
        src = _src_whatsapp_auth()
        bad = [l.strip() for l in src.splitlines() if 'logger.error' in l and '{error_repr}' in l]
        self.assertEqual(
            bad, [],
            f"logger.error com {{error_repr}} no message: {bad}",
        )

    def test_nao_usa_error_traceback_em_logger_error(self):
        """`{error_traceback}` em f-string de logger.error coloca traceback no message."""
        src = _src_whatsapp_auth()
        matches = re.findall(r"logger\.error\(f['\"][^'\"]*\{error_traceback\}", src)
        self.assertEqual(
            matches, [],
            "logger.error(f\"...{error_traceback}...\") coloca traceback completo no message",
        )

    def test_nao_usa_last_error_em_logger_error(self):
        """`{last_error}` em f-string de logger.error coloca str(exc) no message."""
        src = _src_whatsapp_auth()
        matches = re.findall(r"logger\.error\(f['\"][^'\"]*\{last_error\}", src)
        self.assertEqual(
            matches, [],
            "logger.error(f\"...{last_error}...\") expõe str(exception) no campo message",
        )
