"""Regressão: CieloVoucherProvider não deve expor detalhes de exceção nos logs.

Dois vetores cobertos:

1. _procurar_venda_perdida() — captura requests.RequestException em contexto de
   pagamento. O frame contém locals sensíveis: g.public_key, g.api_key (credenciais
   do merchant Cielo). logger.exception() define exc_info=True, o que faz o
   LoggingIntegration do Sentry criar um evento com o traceback completo e locals —
   expondo credenciais ao aggregator sem possibilidade de scrubbing por frame.

2. cobrar() — locals incluem dados (card_token, holder_document, holder_name) e
   payload (corpo completo do POST à Cielo). O mesmo risco se aplica.

O padrão correto para contextos de pagamento: logger.error() sem exc_info, opcionalmente
registrando type(exc).__name__ para triagem. O tipo de exceção (ConnectionError, Timeout,
HTTPError) não contém credenciais.

Todos SimpleTestCase — sem banco, sem rede.
Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
  python3 -m pytest apps/stores/tests/test_cielo_logger_str_exc.py -v
"""
import inspect

from django.test import SimpleTestCase

from apps.stores.services.voucher.cielo import CieloVoucherProvider


class ProcurarVendaLoggerStrExcTest(SimpleTestCase):
    """_procurar_venda_perdida não deve expor locals de pagamento via exc_info."""

    def _src(self):
        return inspect.getsource(CieloVoucherProvider._procurar_venda_perdida)

    def test_nao_usa_logger_exception(self):
        """logger.exception define exc_info=True — captura locals (credenciais) no Sentry."""
        src = self._src()
        self.assertNotIn(
            'logger.exception',
            src,
            'logger.exception inclui exc_info: Sentry captura locals com credenciais Cielo — use logger.error sem exc_info',
        )

    def test_usa_logger_error(self):
        """A falha deve ser registrada com logger.error (sem exc_info)."""
        src = self._src()
        self.assertIn(
            'logger.error',
            src,
            'logger.error ausente em _procurar_venda_perdida — a falha de rede deve ser registrada',
        )


class CobrarLoggerStrExcTest(SimpleTestCase):
    """cobrar() não deve expor locals de pagamento via exc_info."""

    def _src(self):
        return inspect.getsource(CieloVoucherProvider.cobrar)

    def test_nao_usa_logger_exception(self):
        """logger.exception define exc_info=True — captura locals (card_token, credenciais) no Sentry."""
        src = self._src()
        self.assertNotIn(
            'logger.exception',
            src,
            'logger.exception inclui exc_info: Sentry captura locals com dados de pagamento — use logger.error sem exc_info',
        )

    def test_usa_logger_error(self):
        """A falha deve ser registrada com logger.error (sem exc_info)."""
        src = self._src()
        self.assertIn(
            'logger.error',
            src,
            'logger.error ausente em cobrar — a falha de rede deve ser registrada',
        )
