"""
Testes de info-disclosure em payment_views.py — StorePaymentViewSet e MPOAuth callback.

Exceções do SDK do Mercado Pago (e do OAuth de autorização) incluem o corpo completo
da resposta HTTP no str(e). Isso coloca access_token, client_secret e dados de cartão
no campo `message` do log record, burlando qualquer scrubber de campo configurado
no Sentry/CloudWatch/Datadog.

Padrão seguro: logger.exception("mensagem fixa %s", identificador)
  — traceback e str(e) ficam em exc_info (campo separado).

Arquivo coberto: apps/stores/api/payment_views.py
  - StorePaymentViewSet.create
  - StorePaymentViewSet.process
  - StorePaymentViewSet.confirm
  - StorePaymentViewSet.fail
  - StorePaymentViewSet.cancel
  - StorePaymentViewSet.refund
  - MPOAuthCallbackView.get (linha do logger.error com slug, e)
"""
import re
import unittest

PAYMENT_VIEWS = 'apps/stores/api/payment_views.py'

_FSTRING_EXC = re.compile(
    r'logger\.\w+\(f["\'][^\n]*?\{(?:e|exc)\}'
)
_PERCENT_EXC = re.compile(
    r'logger\.\w+\([^\n]+,\s*e\s*\)'
)


def _src():
    with open(PAYMENT_VIEWS, encoding='utf-8') as fh:
        return fh.read()


def _metodo(src, nome):
    """Extrai o corpo do método (até o próximo 'def' no mesmo nível de indentação)."""
    # busca 'def nome(' dentro de uma classe (indentação de 4 espaços)
    pat = re.compile(r'    def ' + re.escape(nome) + r'\(')
    m = pat.search(src)
    if not m:
        return ''
    inicio = m.start()
    # próximo método na mesma classe
    prox = pat.search(src, inicio + 1)
    return src[inicio: prox.start() if prox else len(src)]


class StorePaymentViewSetLoggerTest(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_nenhum_fstring_exc_no_arquivo(self):
        """Nenhum logger.*(f'...{e}') em payment_views.py."""
        achou = _FSTRING_EXC.findall(self.src)
        self.assertEqual(achou, [],
                         f"logger.*( f'...{{e}}') ainda existe em {PAYMENT_VIEWS}: {achou}")

    def test_create_usa_logger_exception(self):
        corpo = _metodo(self.src, 'create')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.create deve usar logger.exception()")

    def test_process_usa_logger_exception(self):
        corpo = _metodo(self.src, 'process')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.process deve usar logger.exception()")

    def test_confirm_usa_logger_exception(self):
        corpo = _metodo(self.src, 'confirm')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.confirm deve usar logger.exception()")

    def test_fail_usa_logger_exception(self):
        corpo = _metodo(self.src, 'fail')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.fail deve usar logger.exception()")

    def test_cancel_usa_logger_exception(self):
        corpo = _metodo(self.src, 'cancel')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.cancel deve usar logger.exception()")

    def test_refund_usa_logger_exception(self):
        corpo = _metodo(self.src, 'refund')
        self.assertIn('logger.exception(', corpo,
                      "StorePaymentViewSet.refund deve usar logger.exception()")


class MPOAuthCallbackLoggerTest(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def _callback_body(self):
        """Extrai o corpo do método get() que trata o callback MP OAuth."""
        m = re.search(r'class MPOAuthCallbackView', self.src)
        if not m:
            # Aceita qualquer callback view com 'oauth' no nome
            m = re.search(r'class\s+\w*[Oo]uth\w*View', self.src)
        if not m:
            return self.src  # fallback: testa o arquivo inteiro
        return self.src[m.start():]

    def test_oauth_callback_nao_usa_percent_e(self):
        """Callback OAuth não deve passar `e` como arg posicional em logger.error."""
        corpo = self._callback_body()
        achou = _PERCENT_EXC.findall(corpo)
        self.assertEqual(achou, [],
                         f"logger.error(..., e) ainda existe no callback OAuth: {achou}")

    def test_oauth_callback_usa_logger_exception(self):
        """Callback OAuth deve usar logger.exception para a troca de código."""
        corpo = self._callback_body()
        self.assertIn('logger.exception(', corpo,
                      "Callback OAuth deve trocar logger.error('%s', slug, e) "
                      "por logger.exception('%s', slug)")
