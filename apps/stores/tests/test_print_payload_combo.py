"""
Comanda (print payload): escolhas do combo precisam sair na impressão e o
endereço não pode duplicar (regressões de 21/07 — cozinha sem saber o sabor).
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreOrderComboItem
from apps.stores.services.print_service import build_order_print_payload


DISPLAY_DATA = {
    'combo_name': 'COMBO SALADA + SUCO',
    'unit_price': '53.99',
    'groups': [
        {'group_name': 'Escolha sua salada:', 'items': [
            {'product_name': 'Tilápia Suprema', 'quantity': 1},
        ]},
        {'group_name': 'Escolha seu suco:', 'items': [
            {'product_name': 'Suco de Acerola 400ml', 'quantity': 1},
        ]},
    ],
}


class PrintPayloadComboTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o', 'o@x.com', 'x')
        self.store = Store.objects.create(
            name='Cê Saladas', slug='ce', owner=self.owner,
            status=Store.StoreStatus.ACTIVE,
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Ana Paula',
            customer_email='ana@x.com', customer_phone='+55 63 99999-0000',
            delivery_address={'street': 'Rua A', 'number': '123',
                              'city': 'Palmas', 'state': 'TO'},
            subtotal=Decimal('53.99'), total=Decimal('53.99'),
        )
        self.item = StoreOrderItem.objects.create(
            order=self.order, product_name='Combo: COMBO SALADA + SUCO',
            sku='', unit_price=Decimal('53.99'), quantity=1,
            options={'selections': {'g1': ['p1'], 'g2': ['p2']}},
        )
        StoreOrderComboItem.objects.create(
            order=self.order, order_item=self.item, combo=None,
            quantity=1, display_data=DISPLAY_DATA,
        )

    def test_combo_ligado_ao_item_sai_com_sabores_nos_details(self):
        payload = build_order_print_payload(self.order)
        self.assertEqual(len(payload['items']), 1)
        details = payload['items'][0]['details']
        self.assertIn('Escolha sua salada:', details)
        self.assertIn('  1x Tilápia Suprema', details)
        self.assertIn('Escolha seu suco:', details)
        self.assertIn('  1x Suco de Acerola 400ml', details)

    def test_sabores_tambem_espelhados_em_ingredients_para_agents_antigos(self):
        payload = build_order_print_payload(self.order)
        ingredients = payload['items'][0]['ingredients']
        self.assertEqual(ingredients, [
            {'role': 'Escolha sua salada', 'name': 'Tilápia Suprema', 'price': 0},
            {'role': 'Escolha seu suco', 'name': 'Suco de Acerola 400ml', 'price': 0},
        ])

    def test_item_sem_combo_tem_ingredients_vazio(self):
        self.order.combo_items.all().delete()
        payload = build_order_print_payload(self.order)
        self.assertEqual(payload['items'][0]['ingredients'], [])
        self.assertEqual(payload['items'][0]['details'], [])

    def test_endereco_nao_duplica_quando_ha_campos_estruturados_e_raw(self):
        self.order.delivery_address = {
            'street': 'Rua A', 'number': '123', 'city': 'Palmas', 'state': 'TO',
            'raw_address': 'Rua A, 123 - Palmas/TO',
        }
        self.order.save(update_fields=['delivery_address'])
        lines = build_order_print_payload(self.order)['address_lines']
        self.assertEqual(lines, ['Rua A, nº 123', 'Palmas / TO'])

    def test_endereco_so_raw_continua_saindo(self):
        self.order.delivery_address = {'raw_address': 'Rua A, 123 - Palmas/TO'}
        self.order.save(update_fields=['delivery_address'])
        lines = build_order_print_payload(self.order)['address_lines']
        self.assertEqual(lines, ['Rua A, 123 - Palmas/TO'])
