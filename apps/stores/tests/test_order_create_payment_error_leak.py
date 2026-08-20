"""
Regressão de segurança: info-disclosure via payment_error = str(exc) em order_create.

Problema: quando o CheckoutService.create_payment lança Exception genérica ao criar
pedido PDV com PIX, o código faz `payment_error = str(exc)` e retorna esse valor
diretamente no corpo da resposta 201 como `data['payment_error']`. Exceções do
gateway de pagamento (MercadoPago, Asaas) podem conter credenciais, URLs internas
ou detalhes de configuração.

Todos os testes são SimpleTestCase (sem DB/Docker).
"""
import inspect

from django.test import SimpleTestCase, override_settings


@override_settings(
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
)
class OrderCreatePaymentErrorLeakTest(SimpleTestCase):
    """order_views não deve expor str(exc) em payment_error."""

    def _order_views_src(self):
        import apps.stores.api.views.order_views as mod
        return inspect.getsource(mod)

    def test_payment_error_nao_usa_str_exc(self):
        """payment_error não deve ser atribuído com str(exc)."""
        src = self._order_views_src()
        self.assertNotIn(
            'payment_error = str(exc)',
            src,
            "order_create ainda usa `payment_error = str(exc)` — "
            "erros do gateway de pagamento vazam no corpo 201.",
        )

    def test_payment_error_nao_usa_str_e_generico(self):
        """Nenhuma variante de str(e) deve ser atribuída a payment_error."""
        import re
        src = self._order_views_src()
        matches = re.findall(r'payment_error\s*=\s*str\s*\([^)]+\)', src)
        self.assertEqual(
            matches,
            [],
            f"payment_error ainda recebe valor de str(): {matches}",
        )

    def test_payment_error_generica_definida_como_mensagem_fixa(self):
        """Após o fix, payment_error deve ser uma string fixa (não str(exc))."""
        src = self._order_views_src()
        # O fix substitui str(exc) por uma mensagem genérica em pt-BR
        # Verifica que existe uma atribuição de payment_error com string literal
        import re
        # Procura padrões como: payment_error = 'Falha ao gerar pagamento PIX'
        fixed = re.findall(
            r"payment_error\s*=\s*['\"][^'\"]+['\"]",
            src,
        )
        self.assertGreater(
            len(fixed),
            0,
            "Esperava payment_error = '<mensagem fixa>' após o fix, mas não encontrou.",
        )
