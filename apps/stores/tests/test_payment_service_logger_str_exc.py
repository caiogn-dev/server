"""
Testes de info-disclosure em payment_service.py e webhooks.py — caminho de pagamento.

Mercado Pago SDK exceptions podem incluir o corpo da resposta da API (mensagens de
erro, status de autorização, referência ao access_token) em str(exc). Interpolá-las
com f-string no campo `message` do logger burla qualquer scrubber de campo
configurado no Sentry/CloudWatch/Datadog.

Padrão seguro: logger.exception("mensagem fixa %s", id) — traceback vai em exc_info
(campo separado), o message fica limpo.

Arquivos cobertos:
  apps/stores/services/payment_service.py  — _process_mercadopago, _refund_mercadopago
  apps/stores/api/webhooks.py              — _send_payment_confirmation_whatsapp
"""
import re
import unittest

PAYMENT_SERVICE = 'apps/stores/services/payment_service.py'
WEBHOOKS = 'apps/stores/api/webhooks.py'

_FSTRING_EXC = re.compile(
    r'logger\.\w+\(f["\'][^\n]*?\{(?:e|exc)\}'
)


def _src(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _metodo(src, nome):
    inicio = src.find(f'def {nome}(')
    if inicio == -1:
        return ''
    prox = src.find('\n    def ', inicio + 1)
    return src[inicio: prox if prox != -1 else len(src)]


class PaymentServiceLoggerTest(unittest.TestCase):
    def setUp(self):
        self.src = _src(PAYMENT_SERVICE)

    def test_nenhum_fstring_com_exc_no_arquivo(self):
        """Nenhum logger.*(f'...{e}') no payment_service inteiro."""
        achou = _FSTRING_EXC.findall(self.src)
        self.assertEqual(achou, [],
                         f"logger.*(f'...{{e}}') ainda existe em {PAYMENT_SERVICE}: {achou}")

    def test_process_mercadopago_usa_logger_exception(self):
        """_process_mercadopago deve usar logger.exception, não logger.error(f'...{e}')."""
        corpo = _metodo(self.src, '_process_mercadopago')
        self.assertIn('logger.exception(', corpo,
                      "_process_mercadopago precisa trocar logger.error(f'...')"
                      " por logger.exception()")

    def test_refund_mercadopago_usa_logger_exception(self):
        """_refund_mercadopago deve usar logger.exception, não logger.error(f'...{e}')."""
        corpo = _metodo(self.src, '_refund_mercadopago')
        self.assertIn('logger.exception(', corpo,
                      "_refund_mercadopago precisa trocar logger.error(f'...')"
                      " por logger.exception()")


class WebhooksLoggerTest(unittest.TestCase):
    def setUp(self):
        self.src = _src(WEBHOOKS)

    def test_send_confirmation_nao_interpola_exc_no_message(self):
        """_send_payment_confirmation_whatsapp não deve ter logger.*(f'...{e}')."""
        corpo = _metodo(self.src, '_send_payment_confirmation_whatsapp')
        achou = _FSTRING_EXC.findall(corpo)
        self.assertEqual(achou, [],
                         f"_send_payment_confirmation_whatsapp tem f-string com "
                         f"{{e}} no logger: {achou}")

    def test_send_confirmation_usa_logger_exception(self):
        """_send_payment_confirmation_whatsapp deve usar logger.exception."""
        corpo = _metodo(self.src, '_send_payment_confirmation_whatsapp')
        self.assertIn('logger.exception(', corpo,
                      "_send_payment_confirmation_whatsapp precisa usar logger.exception()")


class ProcessMercadoPagoFalhaTest(unittest.TestCase):
    """O caminho de erro precisa marcar o pagamento como FAILED e repassar a exceção
    original. Se o `except` perde o `as e` e o corpo ainda usa `e`, sai NameError
    antes do save e o pagamento fica preso em pending."""

    def test_falha_marca_failed_e_repassa_a_excecao_original(self):
        from unittest import mock
        from apps.stores.models import StorePayment
        from apps.stores.services.payment_service import PaymentService

        payment = mock.MagicMock()
        payment.gateway.get_mercadopago_credentials.return_value = None

        with self.assertRaises(ValueError):
            PaymentService()._process_mercadopago(payment)

        self.assertEqual(payment.status, StorePayment.PaymentStatus.FAILED)
        self.assertEqual(payment.error_code, 'mp_error')
        self.assertIn('credentials', payment.error_message)
        payment.save.assert_called()
