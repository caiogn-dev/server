"""N+1 query em _itens: select_related('product') é obrigatório.

Bug (2026-07-27): _itens() usava order.items.all() e acessava item.product
em loop — N queries para N itens. Em PDV com 10 produtos isso são 10 queries
extras na emissão de NFC-e, que corre síncrona no checkout.

Contrato: _itens() deve chamar select_related('product') antes de iterar,
nunca .all() direto seguido de acesso a item.product em loop.

Classes: SimpleTestCase (sem banco) — análise estática + mock.
"""
import ast
import inspect
import re
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

SERVICES_SRC = Path(__file__).parent.parent / 'services.py'


def _itens_source() -> str:
    """Extrai o corpo da função _itens() do arquivo services.py."""
    tree = ast.parse(SERVICES_SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_itens':
            lines = SERVICES_SRC.read_text().splitlines()
            start = node.lineno - 1
            end = node.end_lineno
            return '\n'.join(lines[start:end])
    raise AssertionError('Função _itens não encontrada em services.py')


class ItensSelectRelatedStaticTest(SimpleTestCase):
    """Análise estática: _itens usa select_related('product') — sem banco."""

    def test_select_related_product_presente_em_itens(self):
        """_itens() deve conter select_related('product') antes de iterar."""
        src = _itens_source()
        self.assertIn(
            "select_related('product')",
            src,
            "_itens() não chama select_related('product'). "
            "Sem isso, item.product acessa o banco N vezes — um N+1 por item.",
        )

    def test_items_all_nao_aparece_sem_select_related(self):
        """order.items.all() puro (sem select_related antes) não deve aparecer."""
        src = _itens_source()
        # Procura padrão "items.all()" sem select_related imediatamente antes.
        # Aceita "items.select_related(...).all()" mas rejeita "items.all()" direto.
        naked_all = re.search(r'\.items\.all\(\)', src)
        self.assertIsNone(
            naked_all,
            f"_itens() ainda usa .items.all() sem select_related — N+1 não corrigido. "
            f"Trecho: {naked_all.group() if naked_all else ''}",
        )

    def test_select_related_vem_antes_de_item_product(self):
        """select_related deve aparecer antes do acesso a item.product no código."""
        src = _itens_source()
        idx_select = src.find("select_related('product')")
        idx_access = src.find('item.product')
        self.assertGreater(
            idx_access, idx_select,
            "item.product aparece ANTES de select_related — o prefetch não se aplica.",
        )


class ItensComMockTest(SimpleTestCase):
    """Testes comportamentais: _itens() usa os dados dos itens corretamente."""

    def _make_item(self, idx, sku='SKU1', ncm='21069090'):
        product = MagicMock()
        product.sku = sku
        product.attributes = {'ncm': ncm} if ncm else {}

        item = MagicMock()
        item.product = product
        item.product_name = f'Produto {idx}'
        item.quantity = 1
        item.unit_price = Decimal('25.00')
        item.subtotal = Decimal('25.00')
        return item

    def _run_itens(self, items_list, config=None):
        from apps.fiscal.services import _itens

        order = MagicMock()
        # select_related('product').all() retorna a lista de itens mock
        order.items.select_related.return_value.all.return_value = items_list
        return _itens(order, config or {}, '5102'), order

    def test_select_related_e_chamado_com_product(self):
        """_itens() deve chamar items.select_related('product')."""
        _, order = self._run_itens([self._make_item(1)])
        order.items.select_related.assert_called_once_with('product')

    def test_numero_de_itens_correto(self):
        """_itens() retorna um dict por item."""
        items = [self._make_item(i, sku=f'S{i}') for i in range(1, 4)]
        result, _ = self._run_itens(items)
        self.assertEqual(len(result), 3)

    def test_numero_item_comeca_em_1(self):
        """numero_item é 1-indexed (requisito SEFAZ)."""
        items = [self._make_item(i) for i in range(3)]
        result, _ = self._run_itens(items)
        numeros = [r['numero_item'] for r in result]
        self.assertEqual(numeros, [1, 2, 3])

    def test_codigo_produto_usa_sku(self):
        """codigo_produto deve vir do SKU do produto quando disponível."""
        item = self._make_item(1, sku='MEUSKU')
        result, _ = self._run_itens([item])
        self.assertEqual(result[0]['codigo_produto'], 'MEUSKU')

    def test_ncm_do_produto_e_usado(self):
        """NCM do produto sobrescreve o padrão."""
        item = self._make_item(1, ncm='22021000')
        result, _ = self._run_itens([item])
        self.assertEqual(result[0]['codigo_ncm'], '22021000')

    def test_produto_none_usa_fallback_numerico(self):
        """Item sem produto (produto deletado) usa o índice como código."""
        item = MagicMock()
        item.product = None
        item.product_name = 'Produto Removido'
        item.quantity = 1
        item.unit_price = Decimal('25.00')
        item.subtotal = Decimal('25.00')

        result, _ = self._run_itens([item])
        # Fallback: (product.sku if product else '') or str(idx) → '1'
        self.assertEqual(result[0]['codigo_produto'], '1')

    def test_cfop_propagado_para_todos_os_itens(self):
        """CFOP passado para _itens aparece em todos os registros."""
        items = [self._make_item(i) for i in range(3)]
        result, _ = self._run_itens(items, config={})
        cfops = {r['cfop'] for r in result}
        self.assertEqual(cfops, {'5102'})
