"""
Testes de contrato: telefone e e-mail NÃO podem aparecer em claro nos logs.

Cobre 4 arquivos identificados como PII leak em 2026-08-20:
- apps/whatsapp/intents/handlers/order.py     → phone_number em logger.info
- apps/marketing/services/email_automation_service.py → recipient_email em logger.info
- apps/core/api/lgpd_views.py                → user.email em logger.info / logger.warning
- apps/core/auth_views.py                    → email em logger.info / logger.error

Estratégia: varredura de código-fonte (AST-free) — verifica que as linhas de log
não interpolam PII diretamente. Não requer banco de dados (SimpleTestCase).
"""
import re
from pathlib import Path
from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]


def _src(rel: str) -> str:
    return (REPO_ROOT / rel).read_text()


def _logger_lines_matching(source: str, pattern: re.Pattern) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if pattern.search(line)
    ]


# Padrão: linha de logger que interpolou phone_number em f-string
_PHONE_IN_LOG = re.compile(
    r'logger\.\w+\(f["\'].*\{[^}]*phone_number[^}]*\}',
)

# Padrão: linha de logger que interpolou recipient_email em f-string
_RECIPIENT_EMAIL_IN_LOG = re.compile(
    r'logger\.\w+\(f["\'].*\{[^}]*recipient_email[^}]*\}',
)

# Padrão: linha de logger que interpolou user.email em f-string
_USER_EMAIL_IN_LOG = re.compile(
    r'logger\.\w+\(f["\'].*\{user\.email\}',
)

# Padrão: linha de logger que interpolou variável `email` em f-string
# (apenas em auth_views onde `email` é local PII, não label interno)
_EMAIL_VAR_IN_LOG = re.compile(
    r'logger\.\w+\(f["\'].*\{email\}',
)


class OrderHandlerPhonePIITest(SimpleTestCase):
    """apps/whatsapp/intents/handlers/order.py — phone_number não deve aparecer em logs."""

    source = _src("apps/whatsapp/intents/handlers/order.py")

    def test_no_phone_number_in_logger_fstring(self):
        hits = _logger_lines_matching(self.source, _PHONE_IN_LOG)
        self.assertEqual(
            hits, [],
            f"PII leak: phone_number interpolado em log: {hits}",
        )


class EmailAutomationServicePIITest(SimpleTestCase):
    """apps/marketing/services/email_automation_service.py — recipient_email não deve aparecer em logs."""

    source = _src("apps/marketing/services/email_automation_service.py")

    def test_no_recipient_email_in_logger_fstring(self):
        hits = _logger_lines_matching(self.source, _RECIPIENT_EMAIL_IN_LOG)
        self.assertEqual(
            hits, [],
            f"PII leak: recipient_email interpolado em log: {hits}",
        )


class LGPDViewsPIITest(SimpleTestCase):
    """apps/core/api/lgpd_views.py — user.email não deve aparecer em logs."""

    source = _src("apps/core/api/lgpd_views.py")

    def test_no_user_email_in_logger_fstring(self):
        hits = _logger_lines_matching(self.source, _USER_EMAIL_IN_LOG)
        self.assertEqual(
            hits, [],
            f"PII leak: user.email interpolado em log: {hits}",
        )


class AuthViewsPIITest(SimpleTestCase):
    """apps/core/auth_views.py — variável email não deve aparecer em logs."""

    source = _src("apps/core/auth_views.py")

    def test_no_email_var_in_logger_fstring(self):
        hits = _logger_lines_matching(self.source, _EMAIL_VAR_IN_LOG)
        self.assertEqual(
            hits, [],
            f"PII leak: variável email interpolada em log: {hits}",
        )
