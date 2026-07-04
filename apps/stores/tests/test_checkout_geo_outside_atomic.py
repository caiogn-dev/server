"""Performance/robustez (P0): o cálculo da taxa de entrega (geocode/route via
HTTP Google em UnifiedDeliveryService) rodava DENTRO do @transaction.atomic de
create_order — segurando a conexão do pgbouncer durante I/O de rede externo e
serializando o checkout sob carga.

Este teste prova que `calculate_delivery_fee_for_payload` roda no MESMO nível
de aninhamento transacional do chamador — ou seja, NÃO dentro de um
@transaction.atomic aberto por create_order.

Como o TestCase envolve tudo num atomic (in_atomic_block seria sempre True),
medimos a PROFUNDIDADE de savepoints: um @transaction.atomic aninhado abre um
savepoint novo. Se a chamada geo ocorre na mesma profundidade do chamador, ela
está fora da transação de escrita; se abre +1 nível, está dentro.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreProduct
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class CheckoutGeoOutsideAtomicTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='geo-owner', email='g@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Loja Geo', slug='loja-geo', status=Store.StoreStatus.ACTIVE,
            store_type=Store.StoreType.FOOD, city='Palmas', state='TO',
            default_delivery_fee=Decimal('7.00'),
        )
        self.category = StoreCategory.objects.create(
            store=self.store, name='Saladas', slug='saladas-geo', is_active=True, sort_order=1,
        )
        self.product = StoreProduct.objects.create(
            store=self.store, category=self.category, name='Salada', slug='salada-geo',
            price=Decimal('20.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.cart = StoreCart.objects.create(store=self.store, session_key='geo-cart')
        StoreCartItem.objects.create(cart=self.cart, product=self.product, quantity=1)

    def _customer_data(self):
        return {'name': 'Cliente Geo', 'email': 'c@t.com', 'phone': '+5563999990000'}

    @patch('apps.stores.services.checkout_service.trigger_order_email_automation')
    @patch('apps.stores.services.print_service.enqueue_order_print_job')
    def test_calculo_de_taxa_ocorre_fora_da_transacao(self, _print, _email):
        captured = {}
        baseline_depth = len(connection.savepoint_ids)

        def spy(store, payload):
            captured['depth'] = len(connection.savepoint_ids)
            return {
                'fee': 8.0, 'distance_km': 2.0, 'duration_minutes': 5,
                'is_valid': True, 'available': True, 'message': 'OK', 'zone_name': 'Dinâmica',
            }

        with patch.object(CheckoutService, 'calculate_delivery_fee_for_payload', side_effect=spy):
            order = CheckoutService.create_order(
                cart=self.cart,
                customer_data=self._customer_data(),
                delivery_data={
                    'method': 'delivery',
                    'address': {'street': 'Rua X', 'number': '10', 'neighborhood': 'Centro'},
                },
            )

        self.assertIn('depth', captured, 'a taxa deveria ter sido calculada')
        self.assertEqual(
            captured['depth'], baseline_depth,
            'cálculo de taxa (HTTP geocode/route) NÃO pode rodar dentro do '
            '@transaction.atomic de create_order (abriu savepoint aninhado)',
        )
        # Comportamento preservado: a taxa pré-computada flui para o pedido.
        self.assertEqual(order.delivery_fee, Decimal('8.00'))
        self.assertEqual(order.store_id, self.store.id)
