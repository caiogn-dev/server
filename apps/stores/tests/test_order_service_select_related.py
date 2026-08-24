"""Testes de regressão: select_related em cancel_order e generate_order_summary.

Problema: dois loops em OrderService.cancel_order (restore_stock) e em
generate_order_summary acessam FKs sem select_related, causando N+1:

  cancel_order (restore_stock=True):
    for item in order.items.all():
        item.product.track_stock          # ← N queries por item
    for combo_item in order.combo_items.all():
        combo_item.combo.track_stock      # ← M queries por combo_item

  generate_order_summary:
    for combo_item in order.combo_items.all():
        combo_item.combo.name             # ← M queries por combo_item

Para um pedido com 10 itens e 5 combos o cancel_order sem select_related
dispara 16 queries (1 items + 10 product.track_stock + 1 combo_items +
5 combo.track_stock) em vez de 2 (1 items + 1 combo_items).

Correcao: select_related('product') em items e select_related('combo') em
combo_items nas duas funcoes.

Os testes usam analise estatica do codigo-fonte — sem banco, sem Docker.
"""
import inspect
import unittest


def _source_of(method_name: str) -> str:
    from apps.stores.services.order_service import OrderService
    method = getattr(OrderService, method_name)
    return inspect.getsource(method)


class CancelOrderRestoreStockSelectRelatedTest(unittest.TestCase):
    """cancel_order deve usar select_related para evitar N+1 em restore_stock."""

    def test_items_usa_select_related_product(self):
        """order.items.select_related('product') no loop de restore_stock."""
        src = _source_of('cancel_order')
        self.assertIn(
            "select_related('product')",
            src,
            "cancel_order deve usar select_related('product') nos items para "
            "evitar N queries extras (item.product.track_stock sem prefetch).",
        )

    def test_items_nao_usa_all_puro(self):
        """O loop de items NAO deve usar .items.all() sem select_related."""
        src = _source_of('cancel_order')
        # Verifica que o padrao N+1 (.items.all() sem select_related antes)
        # nao existe no bloco de restore_stock.
        # A presenca de select_related('product') (testada acima) garante isso,
        # mas verificamos explicitamente o padrao ruim:
        lines = [l.strip() for l in src.splitlines()]
        bad_lines = [
            l for l in lines
            if 'order.items.all()' in l and 'select_related' not in l
        ]
        self.assertEqual(
            bad_lines, [],
            f"cancel_order ainda tem 'order.items.all()' sem select_related: {bad_lines}",
        )

    def test_combo_items_usa_select_related_combo_no_restore(self):
        """order.combo_items.select_related('combo') no loop de restore_stock."""
        src = _source_of('cancel_order')
        # A funcao tem dois blocos de combo_items; o do restore usa select_related
        self.assertIn(
            "select_related('combo')",
            src,
            "cancel_order deve usar select_related('combo') em combo_items para "
            "evitar M queries extras (combo_item.combo.track_stock sem prefetch).",
        )


class TextSummarySelectRelatedTest(unittest.TestCase):
    """generate_order_summary deve usar select_related em combo_items."""

    def test_combo_items_usa_select_related_combo(self):
        """order.combo_items.select_related('combo') no generate_order_summary."""
        src = _source_of('generate_order_summary')
        self.assertIn(
            "select_related('combo')",
            src,
            "generate_order_summary deve usar select_related('combo') "
            "em combo_items para evitar M queries (combo_item.combo.name sem prefetch).",
        )

    def test_combo_items_nao_usa_all_puro(self):
        """O loop de combo_items NAO usa .combo_items.all() sem select_related."""
        src = _source_of('generate_order_summary')
        lines = [l.strip() for l in src.splitlines()]
        bad_lines = [
            l for l in lines
            if 'order.combo_items.all()' in l and 'select_related' not in l
        ]
        self.assertEqual(
            bad_lines, [],
            f"generate_order_summary ainda tem 'order.combo_items.all()' sem select_related: {bad_lines}",
        )


class SelectRelatedFunctionalTest(unittest.TestCase):
    """Testa comportamento dos loops com objetos mock — sem banco."""

    def test_cancel_order_acessa_product_via_select_related(self):
        """Simula chamada a cancel_order verificando que product e acessado via prefetch.

        Cria um item mock onde .product ja esta resolvido (como o select_related faz),
        e verifica que track_stock e lido sem nova query de banco.
        """
        from unittest.mock import MagicMock, patch, call
        from decimal import Decimal

        # Mock do produto com track_stock=True
        mock_product = MagicMock()
        mock_product.track_stock = True

        # Mock do item de pedido
        mock_item = MagicMock()
        mock_item.product_id = 'abc123'
        mock_item.product = mock_product  # ja resolvido (como select_related)
        mock_item.quantity = 2

        # Mock do combo_item com combo.track_stock=True
        mock_combo = MagicMock()
        mock_combo.track_stock = True

        mock_combo_item = MagicMock()
        mock_combo_item.combo_id = 'def456'
        mock_combo_item.combo = mock_combo  # ja resolvido
        mock_combo_item.quantity = 1

        # Mock do order
        mock_order = MagicMock()
        mock_order.status = 'pending'
        mock_order.payment_status = 'unpaid'
        mock_order.items.select_related.return_value.all.return_value = [mock_item]
        mock_order.combo_items.select_related.return_value.all.return_value = [mock_combo_item]

        from apps.stores.services.order_service import OrderService
        service = OrderService()

        with patch('apps.stores.models.StoreProduct') as mock_product_model, \
             patch('apps.stores.models.StoreCombo') as mock_combo_model, \
             patch.object(service, '_process_refund', return_value={}), \
             patch.object(service, '_liquidar_pagamento_do_cancelado'), \
             patch.object(service, '_send_status_notification'), \
             patch('apps.stores.services.webhook_service.webhook_service', MagicMock()):
            mock_product_model.objects.filter.return_value.update = MagicMock()
            mock_combo_model.objects.filter.return_value.update = MagicMock()

            result = service.cancel_order(mock_order, restore_stock=True)

        # select_related('product') deve ter sido chamado
        mock_order.items.select_related.assert_called_once_with('product')
        # select_related('combo') deve ter sido chamado
        mock_order.combo_items.select_related.assert_called_once_with('combo')

    def test_text_summary_usa_select_related_combo(self):
        """generate_order_summary chama combo_items.select_related('combo')."""
        from unittest.mock import MagicMock

        # Mock do combo com nome real
        mock_combo = MagicMock()
        mock_combo.name = 'Combo X'

        mock_combo_item = MagicMock()
        mock_combo_item.order_item_id = None
        mock_combo_item.combo = mock_combo
        mock_combo_item.quantity = 1
        mock_combo_item.subtotal = 25.00

        mock_item = MagicMock()
        mock_item.quantity = 2
        mock_item.product_name = 'Produto A'
        mock_item.subtotal = 20.00

        mock_order = MagicMock()
        mock_order.order_number = '001'
        mock_order.customer_name = 'Joao'
        mock_order.customer_phone = '62999999999'
        mock_order.subtotal = 45.00
        mock_order.discount = 0
        mock_order.delivery_fee = 0
        mock_order.total = 45.00
        mock_order.delivery_method = 'pickup'
        mock_order.items.all.return_value = [mock_item]
        mock_order.combo_items.select_related.return_value.all.return_value = [mock_combo_item]

        from apps.stores.services.order_service import OrderService
        service = OrderService()
        result = service.generate_order_summary(mock_order)

        # select_related('combo') deve ter sido chamado
        mock_order.combo_items.select_related.assert_called_once_with('combo')
        # combo_name deve estar no resumo
        self.assertIn('Combo X', result)
