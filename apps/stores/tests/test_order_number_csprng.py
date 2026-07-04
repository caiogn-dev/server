"""
Testes para geração segura do order_number.

O número do pedido usa um sufixo de 4 dígitos decimais (0000-9999).
Antes deste fix, `random.choices` (não-CSPRNG) era usado — apenas 10 mil
possibilidades por prefixo+data, facilitando enumeração.

A correção substitui por `secrets.randbelow(10000)` (CSPRNG), mantendo
o mesmo formato e cardinalidade mas com geração criptograficamente segura.
"""
import re
from unittest.mock import patch
from django.test import SimpleTestCase


# -- helpers ------------------------------------------------------------------

def _make_mock_store(slug='mkt'):
    """Cria um objeto-store mínimo para testar generate_order_number."""
    from unittest.mock import MagicMock
    store = MagicMock()
    store.slug = slug
    return store


def _build_order(slug='mkt'):
    """Instancia StoreOrder sem DB, apenas para chamar generate_order_number.

    StoreOrder.__new__ não chama __init__, então _state precisa ser inicializado
    manualmente. O mock de store é injetado via fields_cache para contornar o
    FK descriptor sem acionar o __set__ (que rejeita não-Store).
    """
    from apps.stores.models.order import StoreOrder
    from django.db.models.base import ModelState
    order = StoreOrder.__new__(StoreOrder)
    order._state = ModelState()
    order._state.fields_cache['store'] = _make_mock_store(slug)
    return order


# -- formato ------------------------------------------------------------------

class TestOrderNumberFormat(SimpleTestCase):
    """O número gerado deve seguir o padrão PREFIX(3) + DATE(6) + SUFFIX(4)."""

    def test_formato_geral(self):
        order = _build_order('cesaladas')
        number = order.generate_order_number()
        # 3 letras maiúsculas + 6 dígitos (AAMMDD) + 4 dígitos
        self.assertRegex(number, r'^[A-Z]{3}\d{6}\d{4}$')

    def test_prefix_derivado_do_slug(self):
        order = _build_order('cesas')
        number = order.generate_order_number()
        self.assertTrue(number.startswith('CES'), number)

    def test_sufixo_tem_4_digitos(self):
        order = _build_order('abc')
        number = order.generate_order_number()
        suffix = number[-4:]
        self.assertEqual(len(suffix), 4)
        self.assertTrue(suffix.isdigit(), f"Sufixo não é numérico: {suffix!r}")

    def test_sufixo_zero_padded(self):
        """Sufixo deve ser zero-padded: secrets.randbelow pode retornar < 1000."""
        order = _build_order('abc')
        with patch('apps.stores.models.order.secrets.randbelow', return_value=7):
            number = order.generate_order_number()
        self.assertEqual(number[-4:], '0007', number)

    def test_sufixo_zero(self):
        """Valor 0 deve virar '0000'."""
        order = _build_order('abc')
        with patch('apps.stores.models.order.secrets.randbelow', return_value=0):
            number = order.generate_order_number()
        self.assertEqual(number[-4:], '0000', number)

    def test_sufixo_maximo(self):
        """Valor 9999 deve virar '9999'."""
        order = _build_order('abc')
        with patch('apps.stores.models.order.secrets.randbelow', return_value=9999):
            number = order.generate_order_number()
        self.assertEqual(number[-4:], '9999', number)


# -- fonte de entropia --------------------------------------------------------

class TestOrderNumberEntropy(SimpleTestCase):
    """O sufixo deve ser gerado via CSPRNG (secrets), não via random."""

    def test_usa_secrets_randbelow(self):
        """secrets.randbelow(10000) deve ser chamado exatamente uma vez."""
        order = _build_order('abc')
        with patch('apps.stores.models.order.secrets.randbelow') as mock_rb:
            mock_rb.return_value = 42
            order.generate_order_number()
        mock_rb.assert_called_once_with(10000)

    def test_nao_usa_random_choices(self):
        """random.choices (não-CSPRNG) NÃO deve ser chamado."""
        order = _build_order('abc')
        with patch('random.choices') as mock_choices:
            order.generate_order_number()
        mock_choices.assert_not_called()

    def test_nao_usa_random_randint(self):
        """random.randint NÃO deve ser chamado."""
        order = _build_order('abc')
        with patch('random.randint') as mock_ri:
            order.generate_order_number()
        mock_ri.assert_not_called()


# -- unicidade probabilística -------------------------------------------------

class TestOrderNumberUniqueness(SimpleTestCase):
    """Chamadas consecutivas devem produzir valores distintos na prática."""

    def test_100_chamadas_sem_repeticao(self):
        """Em 100 chamadas com CSPRNG real, não deve haver colisão."""
        order = _build_order('abc')
        numbers = {order.generate_order_number() for _ in range(100)}
        # Com 10k possibilidades e apenas 100 amostras, colisão é improvável
        self.assertGreater(len(numbers), 90, f"Apenas {len(numbers)} únicos em 100 tentativas")
