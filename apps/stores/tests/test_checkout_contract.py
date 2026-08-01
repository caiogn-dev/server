"""Testes de regressão para contratos do CheckoutService [P1].

Cobre as funções puras de cálculo financeiro do checkout, críticas para corretude
de valores cobrados ao cliente e para validação de e-mail pelo Mercado Pago.

Funções cobertas (todas sem DB/Docker — SimpleTestCase):
  - CheckoutService.calculate_totals()   : subtotal + taxa – desconto = total (≥0)
  - is_placeholder_email()               : identificação de e-mails internos falsos
  - get_valid_email_for_payment()        : fallback de e-mail para o Mercado Pago

Garantias que a suíte protege:
  • O total nunca fica negativo (cláusula max(…, 0)).
  • Desconto maior que subtotal+taxa zera o total, não gera total negativo.
  • E-mails @local.invalid / @whatsapp.bot / @cliente.pastita.com.br são placeholder.
  • E-mails com domínio .local / .test / .invalid são rejeitados pelo MP e o sistema
    usa fallback — evitar cobranças recusadas.
  • A cadeia de fallback para e-mail segue: customer_email → owner.email → cliente@domínio.
"""
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock
from django.test import SimpleTestCase

from apps.stores.services.checkout_service import (
    CheckoutService,
    is_placeholder_email,
    get_valid_email_for_payment,
)


def _cart(subtotal):
    """Retorna um StoreCart mock com subtotal como Decimal."""
    cart = MagicMock()
    cart.subtotal = Decimal(str(subtotal))
    return cart


def _order(email=None, owner_email=None, website_url=''):
    """Monta um StoreOrder mock mínimo para get_valid_email_for_payment."""
    owner = MagicMock()
    owner.email = owner_email

    store = MagicMock()
    store.owner = owner
    store.website_url = website_url

    order = MagicMock(spec=['customer_email', 'store'])
    order.customer_email = email
    order.store = store
    return order


# ---------------------------------------------------------------------------
# CheckoutService.calculate_totals
# ---------------------------------------------------------------------------

class TestCalculateTotalsContrato(SimpleTestCase):
    """Contrato financeiro: total = subtotal + taxa – desconto, mínimo 0."""

    def test_soma_basica(self):
        """100 + 10 – 5 = 105."""
        result = CheckoutService.calculate_totals(
            _cart(100), delivery_fee=Decimal('10'), discount=Decimal('5')
        )
        self.assertAlmostEqual(result['total'], 105.0)
        self.assertAlmostEqual(result['subtotal'], 100.0)
        self.assertAlmostEqual(result['delivery_fee'], 10.0)
        self.assertAlmostEqual(result['discount'], 5.0)

    def test_sem_taxa_padrao_zero(self):
        """Delivery omitido → taxa = 0 → total = subtotal."""
        result = CheckoutService.calculate_totals(_cart(50))
        self.assertAlmostEqual(result['total'], 50.0)
        self.assertAlmostEqual(result['delivery_fee'], 0.0)

    def test_sem_desconto_padrao_zero(self):
        """Discount omitido → desconto = 0 → total = subtotal + taxa."""
        result = CheckoutService.calculate_totals(_cart(50), delivery_fee=Decimal('8'))
        self.assertAlmostEqual(result['total'], 58.0)
        self.assertAlmostEqual(result['discount'], 0.0)

    def test_total_nunca_negativo_desconto_excessivo(self):
        """Desconto maior que subtotal+taxa → total clampeado em 0, não negativo."""
        result = CheckoutService.calculate_totals(
            _cart(30), delivery_fee=Decimal('5'), discount=Decimal('999')
        )
        self.assertEqual(result['total'], 0.0)

    def test_total_nunca_negativo_desconto_exatamente_total(self):
        """Desconto exatamente igual ao total → total = 0."""
        result = CheckoutService.calculate_totals(
            _cart(40), delivery_fee=Decimal('10'), discount=Decimal('50')
        )
        self.assertEqual(result['total'], 0.0)

    def test_imposto_sempre_zero(self):
        """Não há imposto no sistema — campo tax deve ser sempre 0."""
        result = CheckoutService.calculate_totals(_cart(200), delivery_fee=Decimal('15'))
        self.assertEqual(result['tax'], 0)

    def test_sem_taxa_sem_desconto_total_igual_subtotal(self):
        """Retirada sem cupom: total = subtotal."""
        result = CheckoutService.calculate_totals(_cart(75))
        self.assertAlmostEqual(result['total'], 75.0)

    def test_valores_decimais_precisao(self):
        """Precisão decimal mantida em cálculos com centavos."""
        result = CheckoutService.calculate_totals(
            _cart('29.90'), delivery_fee=Decimal('7.50'), discount=Decimal('3.00')
        )
        self.assertAlmostEqual(result['total'], 34.40, places=2)

    def test_subtotal_zero_com_frete(self):
        """Subtotal zero (carrinho vazio/grátis) + frete → total = frete."""
        result = CheckoutService.calculate_totals(
            _cart(0), delivery_fee=Decimal('10')
        )
        self.assertAlmostEqual(result['total'], 10.0)

    def test_todos_zeros(self):
        """Todos os valores zero → total zero (sem crash)."""
        result = CheckoutService.calculate_totals(
            _cart(0), delivery_fee=Decimal('0'), discount=Decimal('0')
        )
        self.assertEqual(result['total'], 0.0)
        self.assertEqual(result['subtotal'], 0.0)
        self.assertEqual(result['delivery_fee'], 0.0)
        self.assertEqual(result['discount'], 0.0)

    def test_chaves_presentes_no_retorno(self):
        """Resposta deve conter exatamente as chaves esperadas pelo frontend."""
        result = CheckoutService.calculate_totals(_cart(100))
        self.assertIn('subtotal', result)
        self.assertIn('delivery_fee', result)
        self.assertIn('tax', result)
        self.assertIn('discount', result)
        self.assertIn('total', result)


# ---------------------------------------------------------------------------
# is_placeholder_email
# ---------------------------------------------------------------------------

class TestIsPlaceholderEmail(SimpleTestCase):
    """Identifica e-mails internos usados como fallback de identidade."""

    def test_local_invalid_e_placeholder(self):
        self.assertTrue(is_placeholder_email('cliente123@local.invalid'))

    def test_whatsapp_bot_e_placeholder(self):
        self.assertTrue(is_placeholder_email('5511999@whatsapp.bot'))

    def test_pastita_local_e_placeholder(self):
        self.assertTrue(is_placeholder_email('joao@cliente.pastita.com.br'))

    def test_none_e_placeholder(self):
        self.assertTrue(is_placeholder_email(None))

    def test_string_vazia_e_placeholder(self):
        self.assertTrue(is_placeholder_email(''))

    def test_email_real_nao_e_placeholder(self):
        self.assertFalse(is_placeholder_email('usuario@gmail.com'))

    def test_email_empresa_nao_e_placeholder(self):
        self.assertFalse(is_placeholder_email('contato@cardapidex.com.br'))

    def test_subdominio_diferente_nao_e_placeholder(self):
        """Subdomínio parecido mas diferente não deve ser identificado como placeholder."""
        self.assertFalse(is_placeholder_email('joao@pastita.com.br'))

    def test_local_sem_invalido_nao_e_placeholder(self):
        """@local sem .invalid não é necessariamente placeholder por esta função."""
        # Nota: get_valid_email_for_payment rejeita .local no domínio separadamente
        self.assertFalse(is_placeholder_email('x@local.com'))


# ---------------------------------------------------------------------------
# get_valid_email_for_payment
# ---------------------------------------------------------------------------

class TestGetValidEmailForPayment(SimpleTestCase):
    """Fallback de e-mail para o Mercado Pago — evita cobranças recusadas."""

    def test_email_real_retornado_diretamente(self):
        """E-mail real do cliente → retornado sem fallback."""
        order = _order(email='cliente@gmail.com', owner_email='lojista@loja.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'cliente@gmail.com')

    def test_email_placeholder_usa_owner(self):
        """E-mail placeholder → fallback para e-mail do dono da loja."""
        order = _order(email='55119@cliente.pastita.com.br', owner_email='dono@loja.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'dono@loja.com')

    def test_email_none_usa_owner(self):
        """E-mail None → fallback para e-mail do dono."""
        order = _order(email=None, owner_email='dono@loja.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'dono@loja.com')

    def test_dominio_local_rejeitado(self):
        """Domínio .local é rejeitado pelo MP — deve usar fallback."""
        order = _order(email='cliente@empresa.local', owner_email='dono@loja.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'dono@loja.com')

    def test_dominio_test_rejeitado(self):
        """Domínio .test é rejeitado pelo MP — deve usar fallback."""
        order = _order(email='dev@minha.test', owner_email='real@owner.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'real@owner.com')

    def test_dominio_invalid_rejeitado(self):
        """Domínio .invalid é rejeitado pelo MP — deve usar fallback."""
        order = _order(email='ghost@local.invalid', owner_email='real@owner.com')
        result = get_valid_email_for_payment(order)
        self.assertEqual(result, 'real@owner.com')

    def test_sem_owner_usa_fallback_padrao(self):
        """Sem dono nem e-mail válido → cliente@noreply.com (fallback final)."""
        order = _order(email=None, owner_email=None)
        order.store.owner.email = None
        result = get_valid_email_for_payment(order)
        self.assertIn('@', result)
        self.assertTrue(result.startswith('cliente@'))

    def test_sem_owner_com_website_usa_dominio_da_loja(self):
        """Sem e-mail de dono, mas loja tem website → usa domínio do site."""
        order = _order(email=None, owner_email=None, website_url='https://minha-loja.com.br')
        order.store.owner.email = None
        result = get_valid_email_for_payment(order)
        self.assertIn('minha-loja.com.br', result)
