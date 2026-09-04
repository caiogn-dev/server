"""Fiscal: N+1 em _itens() — select_related('product') evita 1 query por item.

Antes do fix: 1 SELECT por item (order.items.all() + item.product lazy).
Depois:       1 SELECT total (order.items.select_related('product').all()).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.fiscal.services import build_nfce_payload, get_fiscal_config
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '12.345.678/0001-90',
    'serie': '1',
    'habilitado': True,
}


def _setup_order_with_items(store, n_items: int) -> StoreOrder:
    """Cria pedido com n_items produtos distintos."""
    category = StoreCategory.objects.create(
        store=store, name='Geral', slug=f'geral-{n_items}',
    )
    order = StoreOrder.objects.create(
        store=store,
        customer_name='Cliente Teste',
        customer_phone='11999999999',
        customer_email='x@local.invalid',
        subtotal=10 * n_items,
        total=10 * n_items,
        payment_method='pix',
        delivery_method='pickup',
        status='pending',
        payment_status='paid',
    )
    for i in range(n_items):
        product = StoreProduct.objects.create(
            store=store,
            name=f'Produto {i}',
            price=10,
            track_stock=False,
            category=category,
            sku=f'P{i}-{n_items}',
            attributes={'ncm': '21069090'},
        )
        StoreOrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=10,
            quantity=1,
            subtotal=10,
        )
    return order


class FiscalItemsN1Tests(TestCase):
    """_itens() não deve disparar 1 SELECT por item de pedido."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-fiscal-n1',
            email='owner-fiscal-n1@test.com',
            password='x',
        )
        self.store = Store.objects.create(
            name='Loja N1',
            slug='loja-n1',
            owner=self.owner,
            status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )

    def test_sem_prefetch_usa_select_related_sem_n1(self):
        """Caminho sem prefetch (Celery/emissão direta): 1 query JOIN em vez de 1+N."""
        order = _setup_order_with_items(self.store, n_items=5)
        config = get_fiscal_config(self.store)

        # Máximo aceitável: 1 query para buscar items com JOIN product.
        # Sem select_related seriam 6 queries (1 + 5).
        with self.assertNumQueries(1):
            payload = build_nfce_payload(order, config)

        self.assertEqual(len(payload['itens']), 5)

    def test_com_prefetch_usa_cache_sem_query_adicional(self):
        """Caminho com prefetch (viewset): 0 queries extras — usa _prefetched_objects_cache."""
        from django.db.models import Prefetch
        from apps.stores.models import StoreOrderItem

        order = _setup_order_with_items(self.store, n_items=5)
        # Simula o comportamento do viewset: prefetch_related('items__product')
        order = (
            StoreOrder.objects.prefetch_related('items__product')
            .get(pk=order.pk)
        )
        config = get_fiscal_config(self.store)

        # Com prefetch populado, _itens() não deve emitir nenhuma query.
        with self.assertNumQueries(0):
            payload = build_nfce_payload(order, config)

        self.assertEqual(len(payload['itens']), 5)

    def test_todos_itens_tem_ncm_correto(self):
        """Garante que o select_related não perde atributos do produto."""
        order = _setup_order_with_items(self.store, n_items=3)
        config = get_fiscal_config(self.store)

        payload = build_nfce_payload(order, config)

        for item in payload['itens']:
            self.assertEqual(item['codigo_ncm'], '21069090')

    def test_item_sem_produto_nao_quebra(self):
        """Item com product=None (produto deletado) não deve levantar exceção."""
        order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Cliente Balcão',
            customer_phone='00000000000',
            customer_email='x@local.invalid',
            subtotal=15,
            total=15,
            payment_method='pix',
            delivery_method='pickup',
            status='pending',
            payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=order,
            product=None,
            product_name='Item órfão',
            sku='ORF1',
            unit_price=15,
            quantity=1,
            subtotal=15,
        )

        config = get_fiscal_config(self.store)
        payload = build_nfce_payload(order, config)

        self.assertEqual(len(payload['itens']), 1)
        self.assertEqual(payload['itens'][0]['descricao'], 'Item órfão')
