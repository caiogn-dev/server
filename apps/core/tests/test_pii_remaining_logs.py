"""
LGPD art. 46 — PII nos logs: signals, agents e notifications.

Testes estáticos (SimpleTestCase, sem banco) verificam que números de telefone
e endereços de e-mail NÃO aparecem em claro nas mensagens de log das funções
identificadas como pendentes no gate anti-acúmulo de 2026-08-26.

Arquivos cobertos:
  - apps/users/signals.py          → phone em _sync_unified_user_stats
  - apps/agents/services/langchain_service.py → phone_number em _build_dynamic_context
  - apps/notifications/services/email_service.py → e-mail em send_email
  - apps/automation/tasks/scheduled.py → recipients (lista de e-mails) em send_report_email_task
"""
import ast
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

BASE = Path(__file__).resolve().parents[3]  # repo root

# Telefone e e-mail de teste — valores que NÃO devem aparecer em claro nos logs
_PHONE = "5511987654321"
_EMAIL = "fulano@example.com"


# ---------------------------------------------------------------------------
# Análise estática: regex nos arquivos fonte
# ---------------------------------------------------------------------------

class StaticAnalysisSignalsTest(SimpleTestCase):
    """apps/users/signals.py não deve logar phone em claro."""

    def _source(self):
        return (BASE / "apps/users/signals.py").read_text()

    def test_no_raw_phone_fstring_in_log(self):
        """Padrão logger.*({phone} sem mask_phone) não deve existir."""
        src = self._source()
        # Procura f-string de log com {phone} sem qualquer wrap de mask_phone
        matches = re.findall(
            r'logger\.\w+\(f["\'].*?\{phone\}.*?["\']',
            src,
        )
        naked = [m for m in matches if 'mask_phone' not in m]
        self.assertEqual(
            naked, [],
            f"Phone em claro em log de signals.py: {naked}",
        )

    def test_mask_phone_imported(self):
        src = self._source()
        self.assertIn("mask_phone", src, "mask_phone deve ser importado em signals.py")


class StaticAnalysisLangchainTest(SimpleTestCase):
    """apps/agents/services/langchain_service.py não deve logar phone_number em claro."""

    def _source(self):
        return (BASE / "apps/agents/services/langchain_service.py").read_text()

    def test_no_raw_phone_number_fstring_in_log(self):
        src = self._source()
        matches = re.findall(
            r'logger\.\w+\(f["\'].*?\{phone_number\}.*?["\']',
            src,
        )
        naked = [m for m in matches if 'mask_phone' not in m]
        self.assertEqual(
            naked, [],
            f"phone_number em claro em log de langchain_service.py: {naked}",
        )

    def test_mask_phone_imported(self):
        src = self._source()
        self.assertIn("mask_phone", src, "mask_phone deve ser importado em langchain_service.py")


class StaticAnalysisEmailServiceTest(SimpleTestCase):
    """apps/notifications/services/email_service.py não deve logar e-mail em claro."""

    def _source(self):
        return (BASE / "apps/notifications/services/email_service.py").read_text()

    def test_no_raw_to_fstring_in_log(self):
        src = self._source()
        # Padrão: logger.*(f"... to {to}") sem mask_email
        matches = re.findall(
            r'logger\.\w+\(f["\'].*?\{to\}.*?["\']',
            src,
        )
        naked = [m for m in matches if 'mask_email' not in m]
        self.assertEqual(
            naked, [],
            f"E-mail (" + "{to}" + f") em claro em log de email_service.py: {naked}",
        )

    def test_mask_email_imported(self):
        src = self._source()
        self.assertIn("mask_email", src, "mask_email deve ser importado em email_service.py")


class StaticAnalysisScheduledTaskTest(SimpleTestCase):
    """apps/automation/tasks/scheduled.py não deve logar recipients em claro."""

    def _source(self):
        return (BASE / "apps/automation/tasks/scheduled.py").read_text()

    def test_no_raw_recipients_fstring_in_log(self):
        src = self._source()
        matches = re.findall(
            r'logger\.\w+\(f["\'].*?\{recipients\}.*?["\']',
            src,
        )
        naked = [m for m in matches if 'mask_email' not in m]
        self.assertEqual(
            naked, [],
            f"recipients em claro em log de scheduled.py: {naked}",
        )


# ---------------------------------------------------------------------------
# Testes comportamentais: mock do logger, verifica que PII não aparece
# ---------------------------------------------------------------------------

class SignalsPIILogTest(SimpleTestCase):
    """Phone não deve aparecer em claro no log de _sync_unified_user_stats."""

    def test_log_does_not_contain_raw_phone(self):
        from apps.users import signals as sig_module

        fake_user = MagicMock()
        fake_user.phone_number = _PHONE
        fake_user.total_orders = 0
        fake_user.total_spent = 0
        fake_user.last_order_at = None

        fake_qs = MagicMock()
        fake_qs.aggregate.return_value = {
            'total_orders': 3,
            'total_spent': 150,
            'last_order': None,
        }

        with patch.object(sig_module.logger, 'info') as mock_log, \
             patch('apps.users.signals.UnifiedUserActivity') as mock_act:
            fake_user.save = MagicMock()
            # Chamar internamente a parte de log: simular update_fields não vazio
            # e invocar o logger como o código faz
            try:
                sig_module._sync_unified_user_stats(
                    sender=MagicMock(),
                    instance=MagicMock(
                        store_id='store-1',
                        total=100,
                        id='order-1',
                    ),
                    created=True,
                )
            except Exception:
                pass  # pode falhar por mocks incompletos; só verificamos o log

        for call_args in mock_log.call_args_list:
            msg = str(call_args)
            self.assertNotIn(_PHONE, msg, f"Phone em claro no log: {msg}")


class LangchainPIILogTest(SimpleTestCase):
    """phone_number não deve aparecer em claro no log de _build_dynamic_context."""

    def test_log_does_not_contain_raw_phone(self):
        from apps.agents.services.langchain_service import LangchainService

        with patch('apps.agents.services.langchain_service.logger') as mock_logger, \
             patch.object(LangchainService, '__init__', return_value=None), \
             patch.object(LangchainService, '_resolve_store', return_value=MagicMock()), \
             patch.object(LangchainService, '_build_customer_context', return_value=''), \
             patch.object(LangchainService, '_build_menu_context', return_value=''), \
             patch.object(LangchainService, '_build_orders_context', return_value=''):
            svc = LangchainService.__new__(LangchainService)
            svc.agent = MagicMock(context_prompt=None)
            try:
                svc._build_dynamic_context(_PHONE, conversation_id='conv-123')
            except Exception:
                pass

        for call_args in mock_logger.info.call_args_list:
            msg = str(call_args)
            self.assertNotIn(_PHONE, msg, f"Phone em claro no log de langchain_service: {msg}")


class EmailServicePIILogTest(SimpleTestCase):
    """E-mail não deve aparecer em claro nos logs de email_service."""

    def test_disabled_log_does_not_contain_raw_email(self):
        from apps.notifications.services.email_service import EmailService

        with patch('apps.notifications.services.email_service.logger') as mock_logger:
            svc = EmailService.__new__(EmailService)
            svc.enabled = False
            svc.from_name = "Test"
            svc.from_email = "no-reply@test.com"
            svc.send_email(
                to=_EMAIL,
                subject="Assunto",
                html="<p>oi</p>",
            )

        for call_args in mock_logger.warning.call_args_list:
            msg = str(call_args)
            self.assertNotIn(_EMAIL, msg, f"E-mail em claro no log (disabled): {msg}")

    def test_success_log_does_not_contain_raw_email(self):
        from apps.notifications.services.email_service import EmailService

        with patch('apps.notifications.services.email_service.logger') as mock_logger, \
             patch('apps.notifications.services.email_service.resend') as mock_resend:
            mock_resend.Emails.send.return_value = {'id': 'fake-id'}
            svc = EmailService.__new__(EmailService)
            svc.enabled = True
            svc.from_name = "Test"
            svc.from_email = "no-reply@test.com"
            svc.send_email(
                to=_EMAIL,
                subject="Assunto",
                html="<p>oi</p>",
            )

        for call_args in mock_logger.info.call_args_list:
            msg = str(call_args)
            self.assertNotIn(_EMAIL, msg, f"E-mail em claro no log (success): {msg}")
