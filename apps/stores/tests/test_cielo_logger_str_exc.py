"""Regressão: CieloVoucherProvider não deve interpolar str(exc) na mensagem do logger.

Dois vetores cobertos:

1. _procurar_venda_perdida() — captura requests.RequestException e registra
   `logger.error('[cielo] ... : %s', order.id, erro)`.
   `requests.RequestException` (e suas subclasses: ConnectionError, Timeout,
   HTTPError) inclui URL interna da Cielo, query params com order_id e, em
   HTTPError, o corpo da resposta que pode conter dados de pagamento.
   Interpolar `str(erro)` na mensagem do log (campo 'message') expõe esses
   detalhes em agregadores como Sentry sem possibilidade de scrubbing por campo.

2. cobrar() — mesmo padrão em `logger.error('[cielo] POST ... falhou: %s', ..., erro)`.

O padrão correto é `logger.exception('...')` que registra o traceback em
`exc_info` (campo separado no log record), onde redatores de campo funcionam.

Todos SimpleTestCase — sem banco, sem rede.
Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
  python3 -m pytest apps/stores/tests/test_cielo_logger_str_exc.py -v
"""
import inspect

from django.test import SimpleTestCase

from apps.stores.services.voucher.cielo import CieloVoucherProvider


class ProcurarVendaLoggerStrExcTest(SimpleTestCase):
    """_procurar_venda_perdida não deve interpolar str(exc) na mensagem do logger."""

    def _src(self):
        return inspect.getsource(CieloVoucherProvider._procurar_venda_perdida)

    def test_nao_usa_logger_error_com_excecao(self):
        """logger.error com a exceção como argumento posicional deve estar ausente."""
        src = self._src()
        self.assertNotIn(
            'logger.error',
            src,
            'logger.error interpola str(exc) na mensagem — use logger.exception',
        )

    def test_usa_logger_exception(self):
        """logger.exception deve ser o padrão — coloca exc_info no campo separado."""
        src = self._src()
        self.assertIn(
            'logger.exception',
            src,
            'logger.exception ausente em _procurar_venda_perdida',
        )


class CobrarLoggerStrExcTest(SimpleTestCase):
    """cobrar() não deve interpolar str(exc) na mensagem do logger."""

    def _src(self):
        return inspect.getsource(CieloVoucherProvider.cobrar)

    def test_nao_usa_logger_error_com_excecao(self):
        """logger.error com a exceção como argumento posicional deve estar ausente."""
        src = self._src()
        self.assertNotIn(
            'logger.error',
            src,
            'logger.error interpola str(exc) na mensagem — use logger.exception',
        )

    def test_usa_logger_exception(self):
        """logger.exception deve ser o padrão."""
        src = self._src()
        self.assertIn(
            'logger.exception',
            src,
            'logger.exception ausente em cobrar',
        )
