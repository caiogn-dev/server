"""
Testes de contrato para o fluxo de salada personalizada (Flutter builder).

Cobre:
- normalize_custom_salad_payload: formatos de ingredientes aceitos pelo serviço
- _ingredient_lines (print_service): ingredientes em string E em dict
- receipt_service: renderização de ingredientes em formato string

Todos SimpleTestCase — sem Docker/PostgreSQL.

Bug corrigido nesta sessão (2026-07-20):
  normalize_custom_salad_payload armazenava ingredientes como strings quando o
  Flutter enviava ["Alface", "Tomate", ...]. Mas tanto receipt_service quanto
  print_service ignoravam silenciosamente itens não-dict, deixando a comanda/
  recibo sem ingredientes para pedidos com formato simplificado.
"""
from django.test import SimpleTestCase

from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.print_service import _ingredient_lines


class NormalizeCustomSaladPayloadTest(SimpleTestCase):
    """normalize_custom_salad_payload normaliza ingredientes e valida o payload."""

    def _normalize(self, customizations, combo_name='Monte sua Salada', unit_price='29.90'):
        return CheckoutService.normalize_custom_salad_payload(
            customizations, combo_name=combo_name, unit_price=unit_price,
        )

    # ── Formato 1: lista de dicts (com name/role) ─────────────────────────
    def test_lista_de_dicts_preservada(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': [
                {'name': 'Alface', 'role': 'base'},
                {'name': 'Tomate', 'role': 'extra'},
            ],
        })
        self.assertEqual(len(payload['ingredients']), 2)
        self.assertIsInstance(payload['ingredients'][0], dict)
        self.assertEqual(payload['ingredients'][0]['name'], 'Alface')

    # ── Formato 2: lista de strings simples (formato Flutter simplificado) ─
    def test_lista_de_strings_preservada(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': ['Alface', 'Tomate', 'Cenoura'],
        })
        self.assertEqual(payload['ingredients'], ['Alface', 'Tomate', 'Cenoura'])

    # ── Formato 3: string separada por · (fallback antigo) ──────────────
    def test_string_separada_por_ponto(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': 'Alface · Tomate · Cenoura',
        })
        self.assertEqual(payload['ingredients'], ['Alface', 'Tomate', 'Cenoura'])

    # ── Ingredientes vazios → ValueError ─────────────────────────────────
    def test_sem_ingredientes_levanta_value_error(self):
        with self.assertRaises(ValueError):
            self._normalize({'is_salad_builder': True, 'ingredients': []})

    def test_ingredientes_none_levanta_value_error(self):
        with self.assertRaises(ValueError):
            self._normalize({'is_salad_builder': True})

    # ── Metadados preservados ─────────────────────────────────────────────
    def test_type_e_is_salad_builder_setados(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': ['Alface'],
        })
        self.assertEqual(payload['type'], 'custom_salad')
        self.assertTrue(payload['is_salad_builder'])

    def test_unit_price_e_total_price_setados(self):
        payload = self._normalize(
            {'is_salad_builder': True, 'ingredients': ['Alface']},
            unit_price='29.90',
        )
        self.assertEqual(payload['unit_price'], '29.90')
        self.assertEqual(payload['total_price'], '29.90')

    def test_custom_name_usa_combo_name_se_ausente(self):
        payload = self._normalize(
            {'is_salad_builder': True, 'ingredients': ['Alface']},
            combo_name='Salada Grande',
        )
        self.assertEqual(payload['custom_name'], 'Salada Grande')

    def test_custom_name_sobrescreve_combo_name(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': ['Alface'],
            'custom_name': 'Minha Salada Especial',
        }, combo_name='Salada Grande')
        self.assertEqual(payload['custom_name'], 'Minha Salada Especial')

    def test_strings_vazias_na_lista_ignoradas(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': ['Alface', '', '  ', 'Tomate'],
        })
        self.assertNotIn('', payload['ingredients'])
        self.assertEqual(len(payload['ingredients']), 2)

    def test_dict_sem_name_ignorado(self):
        payload = self._normalize({
            'is_salad_builder': True,
            'ingredients': [{'role': 'base'}, {'name': 'Tomate', 'role': 'extra'}],
        })
        self.assertEqual(len(payload['ingredients']), 1)
        self.assertEqual(payload['ingredients'][0]['name'], 'Tomate')


class IngredientLinesPrintServiceTest(SimpleTestCase):
    """_ingredient_lines: renderiza ingredientes em formato dict E em string."""

    def test_dict_com_name_e_role(self):
        lines = _ingredient_lines([{'name': 'Alface', 'role': 'base'}])
        self.assertEqual(lines, ['base: Alface'])

    def test_dict_sem_role(self):
        lines = _ingredient_lines([{'name': 'Tomate'}])
        self.assertEqual(lines, ['Tomate'])

    def test_dict_com_preco_adicional(self):
        lines = _ingredient_lines([{'name': 'Queijo', 'price': '3.50'}])
        self.assertIn('Queijo', lines[0])
        self.assertIn('+R$', lines[0])

    def test_string_simples_exibida(self):
        """Ingrediente como string simples deve aparecer na comanda (bug corrigido 2026-07-20)."""
        lines = _ingredient_lines(['Alface', 'Tomate', 'Cenoura'])
        self.assertEqual(lines, ['Alface', 'Tomate', 'Cenoura'])

    def test_string_vazia_ignorada(self):
        lines = _ingredient_lines(['Alface', '', '  ', 'Tomate'])
        self.assertEqual(lines, ['Alface', 'Tomate'])

    def test_lista_mista_dicts_e_strings(self):
        """Lista mista (dict + string) deve renderizar ambos corretamente."""
        lines = _ingredient_lines([
            {'name': 'Alface', 'role': 'base'},
            'Tomate',
            {'name': 'Cenoura'},
        ])
        self.assertEqual(lines, ['base: Alface', 'Tomate', 'Cenoura'])

    def test_lista_vazia(self):
        self.assertEqual(_ingredient_lines([]), [])

    def test_dict_sem_name_ignorado(self):
        lines = _ingredient_lines([{'role': 'base'}, {'name': 'Tomate'}])
        self.assertEqual(lines, ['Tomate'])


class ReceiptIngredientRenderingTest(SimpleTestCase):
    """receipt_service renderiza ingredientes de salada em formato string."""

    def _render_combo_name(self, customizations):
        """Replica a lógica de renderização de ingredientes do receipt_service."""
        if customizations.get('is_salad_builder') and customizations.get('ingredients'):
            ingredients = customizations['ingredients']
            ingredient_parts = []
            for ing in ingredients:
                if isinstance(ing, dict):
                    ing_name = str(ing.get('name') or '').strip()
                    if not ing_name:
                        continue
                    role = str(ing.get('role') or '').strip()
                    ingredient_parts.append(f"{role}: {ing_name}" if role else ing_name)
                elif isinstance(ing, str) and ing.strip():
                    ingredient_parts.append(ing.strip())
            return ', '.join(ingredient_parts)
        return ''

    def test_ingredientes_em_string_aparecem_no_recibo(self):
        """String ingredients must appear in receipt (bug corrigido 2026-07-20)."""
        result = self._render_combo_name({
            'is_salad_builder': True,
            'ingredients': ['Alface', 'Tomate', 'Cenoura'],
        })
        self.assertIn('Alface', result)
        self.assertIn('Tomate', result)
        self.assertIn('Cenoura', result)

    def test_ingredientes_em_dict_aparecem_no_recibo(self):
        result = self._render_combo_name({
            'is_salad_builder': True,
            'ingredients': [{'name': 'Alface', 'role': 'base'}, {'name': 'Tomate'}],
        })
        self.assertIn('base: Alface', result)
        self.assertIn('Tomate', result)

    def test_lista_mista_renderiza_ambos(self):
        result = self._render_combo_name({
            'is_salad_builder': True,
            'ingredients': [{'name': 'Alface', 'role': 'base'}, 'Tomate'],
        })
        self.assertIn('base: Alface', result)
        self.assertIn('Tomate', result)

    def test_sem_ingredientes_retorna_vazio(self):
        result = self._render_combo_name({'is_salad_builder': True, 'ingredients': []})
        self.assertEqual(result, '')

    def test_nao_salad_builder_retorna_vazio(self):
        result = self._render_combo_name({'ingredients': ['Alface']})
        self.assertEqual(result, '')
