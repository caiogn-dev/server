"""
LGPD art. 46 — PII jamais deve aparecer em claro nos logs de produção.

Cobre dois pontos em apps/stores/services/checkout_service.py:

  1. L1511 — logger.info(f"Using email for payment: {payer_email}")
     → e-mail do cliente em claro no caminho de criação de pagamento PIX/cartão.

  2. L516 — logger.info(f"calculate_delivery_fee_for_payload: ..., address_text={address_text}")
     → endereço residencial do cliente em claro no caminho de cálculo de frete.

Ambos os testes usam SimpleTestCase (sem banco de dados).
"""
import re
from pathlib import Path
from django.test import SimpleTestCase

CHECKOUT_PATH = (
    Path(__file__).resolve().parents[1] / "services" / "checkout_service.py"
)


def _read_source() -> str:
    return CHECKOUT_PATH.read_text(encoding="utf-8")


def _logger_lines(source: str) -> list[str]:
    """Retorna todas as linhas com chamadas de logger no source."""
    return [
        line.strip()
        for line in source.splitlines()
        if re.search(r'logger\.(info|debug|warning|error|critical)', line)
    ]


class CheckoutServiceEmailPIITest(SimpleTestCase):
    """Garante que payer_email não aparece em claro em nenhum logger do checkout_service."""

    def setUp(self):
        self.source = _read_source()
        self.logger_lines = _logger_lines(self.source)

    def test_payer_email_not_interpolated_raw_in_any_logger_line(self):
        """Nenhuma linha de logger deve interpolar {payer_email} sem mask_email."""
        leaks = [
            line for line in self.logger_lines
            if re.search(r'\{payer_email', line) and 'mask_email' not in line
        ]
        self.assertFalse(
            leaks,
            "PII leak: payer_email em claro em logger do checkout_service:\n"
            + "\n".join(leaks),
        )

    def test_email_string_not_logged_raw_as_format_arg(self):
        """logger.info('... email ...', payer_email) sem máscara também não é permitido."""
        leaks = [
            line for line in self.logger_lines
            if (
                re.search(r'["\'].*[Ee]mail.*["\'].*payer_email', line)
                and 'mask_email' not in line
            )
        ]
        self.assertFalse(
            leaks,
            "PII leak: payer_email como argumento de format sem mask_email:\n"
            + "\n".join(leaks),
        )

    def test_mask_email_imported_in_checkout_service(self):
        """mask_email deve estar importada no checkout_service para cobrir os logs."""
        self.assertIn(
            'mask_email',
            self.source,
            "mask_email não encontrada em checkout_service.py — "
            "logs de e-mail provavelmente estão em claro.",
        )


class CheckoutServiceAddressPIITest(SimpleTestCase):
    """Garante que address_text do cliente não aparece em claro em logger do checkout_service."""

    def setUp(self):
        self.source = _read_source()
        self.logger_lines = _logger_lines(self.source)

    def test_address_text_not_interpolated_raw_in_any_logger_line(self):
        """Nenhuma linha de logger deve interpolar {address_text} em claro."""
        leaks = [
            line for line in self.logger_lines
            if re.search(r'\{address_text\}', line)
        ]
        self.assertFalse(
            leaks,
            "PII leak: address_text (endereço do cliente) em claro em logger:\n"
            + "\n".join(leaks),
        )

    def test_address_text_not_as_format_arg(self):
        """address_text não deve aparecer como argumento de format em logger sem máscara."""
        leaks = [
            line for line in self.logger_lines
            if (
                'address_text' in line
                and not re.search(r'address_(provided|len|truncated)', line)
            )
        ]
        self.assertFalse(
            leaks,
            "PII leak: address_text como argumento de logger sem ofuscação:\n"
            + "\n".join(leaks),
        )
