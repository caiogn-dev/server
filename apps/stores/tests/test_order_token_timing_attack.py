"""Regressão P1: comparação de token de pedido deve usar hmac.compare_digest.

PaymentStatusView e CustomerOrderDetailView aceitavam ?token=<access_token>
com comparação Python direta (`token == order.access_token`). Uma comparação
de strings de comprimento variável em Python vaza tempo proporcional ao
prefixo comum, abrindo timing attack contra quem souber o UUID do pedido.

Correção: usar `hmac.compare_digest(str(token), str(order.access_token))`
em ambas as views.

Referências na base:
  - fix/token-timing-attack
  - fix/security-timing-attack-tokens
  - fix/messenger-token-timing-attack
"""
import inspect

from django.test import SimpleTestCase

from apps.stores.api.webhooks import CustomerOrderDetailView, PaymentStatusView


def _src(cls, method):
    return inspect.getsource(getattr(cls, method))


class PaymentStatusViewTimingTest(SimpleTestCase):
    """PaymentStatusView.get() não deve comparar token com == diretamente."""

    def _src(self):
        return _src(PaymentStatusView, 'get')

    def test_usa_compare_digest(self):
        """Deve chamar hmac.compare_digest para comparar o token."""
        self.assertIn(
            'compare_digest',
            self._src(),
            "PaymentStatusView.get() compara token com == em vez de "
            "hmac.compare_digest — timing attack possível.",
        )

    def test_nao_usa_comparacao_direta(self):
        """Não deve conter `token == order.access_token` literal."""
        self.assertNotIn(
            'token == order.access_token',
            self._src(),
            "PaymentStatusView.get() usa comparação direta de token — "
            "substitua por hmac.compare_digest.",
        )


class CustomerOrderDetailViewTimingTest(SimpleTestCase):
    """CustomerOrderDetailView.get() não deve comparar token com == diretamente."""

    def _src(self):
        return _src(CustomerOrderDetailView, 'get')

    def test_usa_compare_digest(self):
        """Deve chamar hmac.compare_digest para comparar o token."""
        self.assertIn(
            'compare_digest',
            self._src(),
            "CustomerOrderDetailView.get() compara token com == em vez de "
            "hmac.compare_digest — timing attack possível.",
        )

    def test_nao_usa_comparacao_direta(self):
        """Não deve conter `token == order.access_token` literal."""
        self.assertNotIn(
            'token == order.access_token',
            self._src(),
            "CustomerOrderDetailView.get() usa comparação direta de token — "
            "substitua por hmac.compare_digest.",
        )
