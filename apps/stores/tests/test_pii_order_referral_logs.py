"""
LGPD art. 46 — telefones e PII jamais devem aparecer em claro nos logs.

Cobre dois módulos novos que introduziram violações:
  1. apps/stores/models/order.py  — _trigger_status_whatsapp_notification
     loga customer_phone e phone normalizados em claro (3 locais).
  2. apps/stores/services/referral_service.py — _notify_referrer
     loga o telefone do indicador em claro no warning de falha.

Todos os testes usam SimpleTestCase (sem banco de dados).
"""
import ast
import os
import re
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

from apps.core.pii import mask_phone

PHONE = '5511999887766'

# ---------------------------------------------------------------------------
# Análise estática de apps/stores/models/order.py
# Verifica que nenhuma f-string de logger expõe {self.customer_phone} ou
# {phone} sem passar por mask_phone.
# ---------------------------------------------------------------------------

ORDER_MODULE_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'models', 'order.py'
)


def _logger_fstring_leaks(source: str) -> list[str]:
    """Retorna linhas em que logger.*(...) tem {phone} ou {customer_phone} em claro."""
    leaks = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if not re.search(r'logger\.(info|warning|debug|error|critical)', stripped):
            continue
        # Padrão proibido: interpolação de phone sem mask_phone
        if re.search(r'\{self\.customer_phone\}|\{phone\}', stripped):
            # Permitido se mask_phone está na mesma linha
            if 'mask_phone' not in stripped:
                leaks.append(f'L{i}: {stripped}')
    return leaks


class OrderModelPiiStaticAnalysisTest(SimpleTestCase):
    """Análise estática do source de order.py para garantir que logs de
    WhatsApp não expõem telefones em claro."""

    def setUp(self):
        path = os.path.normpath(os.path.join(os.path.dirname(__file__), ORDER_MODULE_PATH))
        with open(path, encoding='utf-8') as fh:
            self.source = fh.read()

    def test_no_customer_phone_in_logger_fstrings(self):
        """Nenhum logger deve interpolar {self.customer_phone} sem máscara."""
        leaks = [
            line for line in _logger_fstring_leaks(self.source)
            if 'customer_phone' in line
        ]
        self.assertFalse(
            leaks,
            f"PII (customer_phone) exposto em log sem mask_phone:\n" + '\n'.join(leaks),
        )

    def test_no_raw_phone_var_in_logger_fstrings(self):
        """`phone` local normalizado também precisa de máscara antes de logar."""
        leaks = [
            line for line in _logger_fstring_leaks(self.source)
            if re.search(r'\{phone\}', line) and 'customer_phone' not in line
        ]
        self.assertFalse(
            leaks,
            f"PII (variável phone) exposta em log sem mask_phone:\n" + '\n'.join(leaks),
        )

    def test_mask_phone_imported_or_used_in_whatsapp_notification(self):
        """mask_phone deve ser referenciada no módulo para cobrir os logs de telefone."""
        self.assertIn(
            'mask_phone',
            self.source,
            "mask_phone não encontrada em order.py — logs de telefone provavelmente estão em claro",
        )


# ---------------------------------------------------------------------------
# Teste comportamental de referral_service._notify_referrer
# Quando o envio de WhatsApp falha, o warning NÃO deve logar o phone em claro.
# ---------------------------------------------------------------------------

class ReferralServiceNotifyLogMaskingTest(SimpleTestCase):
    """_notify_referrer deve mascarar o telefone do indicador no log de falha."""

    def _run_notify_with_failure(self):
        """Simula _notify_referrer onde MessageService.send_text_message levanta."""
        from apps.stores.services.referral_service import ReferralService

        store = MagicMock()
        account = MagicMock()
        account.phone_number_id = 'ph123'
        store.get_whatsapp_account.return_value = account

        reward = MagicMock()
        reward.code = 'AMIGO5-TEST'
        reward.valid_until.strftime.return_value = '31/12'

        with patch('apps.whatsapp.services.MessageService') as MockMS:
            MockMS.return_value.send_text_message.side_effect = RuntimeError('conexão falhou')
            with self.assertLogs('apps.stores.services.referral_service', level='WARNING') as cm:
                ReferralService._notify_referrer(store, PHONE, reward)
        return cm.output

    def test_phone_not_in_failure_log(self):
        """O telefone em claro não deve aparecer no warning de falha de notificação."""
        logs = self._run_notify_with_failure()
        for line in logs:
            self.assertNotIn(
                PHONE, line,
                f"Telefone do indicador vazou em log de falha: {line}",
            )

    def test_masked_phone_in_failure_log(self):
        """O telefone mascarado DEVE aparecer no warning (rastreabilidade)."""
        logs = self._run_notify_with_failure()
        masked = mask_phone(PHONE)
        all_logs = ' '.join(logs)
        self.assertIn(
            masked, all_logs,
            f"Telefone mascarado ({masked}) não encontrado no log de falha — "
            "adicione mask_phone ao warning para manter rastreabilidade",
        )
