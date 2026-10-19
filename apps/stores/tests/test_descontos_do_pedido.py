"""De ONDE veio o desconto do pedido — cupom, resgate da fidelidade, cashback.

19/10, dono: "não consigo ver qual cupom foi utilizado pelo cliente na
comanda", e o resgate do item grátis aparecia só como "Desconto". O pedido
grava um `discount` somado; as partes moram em `coupon_code`,
`metadata.loyalty_reward` e `metadata.cashback_aplicado`. Esta função separa,
e painel, comanda do painel e print agent leem dela.

O valor do cupom não é gravado à parte: é o que sobra do desconto depois do
resgate e do cashback. Se a conta não fecha (pedido editado à mão depois),
nada é inventado — sai uma linha só, "Desconto", com o total.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.services.descontos_do_pedido import descontos_do_pedido

User = get_user_model()


class DescontosDoPedidoTests(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-desc', password='x')
        self.loja = Store.objects.create(owner=dono, name='Cê', slug='ce-desc', status='active')
        cat = StoreCategory.objects.create(store=self.loja, name='Saladas', slug='saladas')
        self.salmao = StoreProduct.objects.create(
            store=self.loja, category=cat, name='Salmão Sublime', slug='salmao',
            price=Decimal('52.90'), track_stock=False,
        )
        self.queridinha = StoreProduct.objects.create(
            store=self.loja, category=cat, name='Queridinha', slug='queridinha',
            price=Decimal('36.99'), track_stock=False,
        )

    def _pedido(self, *, itens, discount='0', coupon_code='', metadata=None, **extra):
        subtotal = sum(Decimal(str(p.price)) * q for p, q in itens)
        pedido = StoreOrder.objects.create(
            store=self.loja, customer_name='Cliente', customer_phone='63999990000',
            subtotal=subtotal, discount=Decimal(discount), total=subtotal - Decimal(discount),
            coupon_code=coupon_code, metadata=metadata or {}, **extra,
        )
        for produto, qtd in itens:
            StoreOrderItem.objects.create(
                order=pedido, product=produto, product_name=produto.name,
                unit_price=produto.price, quantity=qtd, subtotal=produto.price * qtd,
            )
        return pedido

    def test_sem_desconto_lista_vazia(self):
        self.assertEqual(descontos_do_pedido(self._pedido(itens=[(self.salmao, 1)])), [])

    def test_cupom_mostra_o_codigo_e_o_valor(self):
        pedido = self._pedido(itens=[(self.salmao, 1)], discount='5.29', coupon_code='BEMVINDO10')
        self.assertEqual(descontos_do_pedido(pedido), [
            {'tipo': 'cupom', 'rotulo': 'Cupom BEMVINDO10', 'valor': '5.29', 'codigo': 'BEMVINDO10'},
        ])

    def test_resgate_diz_qual_item_saiu_gratis(self):
        """Wanny, CE-2610192528: Salmão pelo resgate."""
        pedido = self._pedido(
            itens=[(self.salmao, 1)], discount='52.90',
            metadata={'loyalty_reward': {'applied': True, 'count': 1, 'discount': 52.9}},
        )
        self.assertEqual(descontos_do_pedido(pedido), [{
            'tipo': 'fidelidade', 'rotulo': 'Resgate fidelidade',
            'valor': '52.90', 'item': 'Salmão Sublime',
        }])

    def test_resgate_aponta_a_salada_de_mesmo_preco_entre_varias(self):
        pedido = self._pedido(
            itens=[(self.salmao, 1), (self.queridinha, 1)], discount='36.99',
            metadata={'loyalty_reward': {'applied': True, 'count': 1, 'discount': 36.99}},
        )
        self.assertEqual(descontos_do_pedido(pedido)[0]['item'], 'Queridinha')

    def test_cupom_resgate_e_cashback_viram_tres_linhas(self):
        # 13/10, dono testando: cupom 5% + grátis — o servidor soma tudo em `discount`.
        pedido = self._pedido(
            itens=[(self.salmao, 1), (self.queridinha, 1)], discount='42.84',
            coupon_code='NUTRI.TANIA',
            metadata={
                'loyalty_reward': {'applied': True, 'count': 1, 'discount': 36.99},
                'cashback_aplicado': 1.5,
            },
        )
        linhas = descontos_do_pedido(pedido)
        self.assertEqual([l['tipo'] for l in linhas], ['cupom', 'fidelidade', 'cashback'])
        self.assertEqual(linhas[0]['valor'], '4.35')
        self.assertEqual(linhas[2], {'tipo': 'cashback', 'rotulo': 'Cashback usado', 'valor': '1.50'})

    def test_desconto_sem_cupom_mostra_o_motivo_de_quem_editou(self):
        pedido = self._pedido(
            itens=[(self.salmao, 1)], discount='10.00', manual_discount_reason='Atraso na entrega',
        )
        self.assertEqual(descontos_do_pedido(pedido), [
            {'tipo': 'manual', 'rotulo': 'Desconto: Atraso na entrega', 'valor': '10.00'},
        ])

    def test_conta_que_nao_fecha_nao_inventa_partes(self):
        """Editaram o desconto para MENOS que o resgate: uma linha só, com o total."""
        pedido = self._pedido(
            itens=[(self.salmao, 1)], discount='20.00', coupon_code='X',
            metadata={'loyalty_reward': {'applied': True, 'count': 1, 'discount': 52.9}},
        )
        self.assertEqual(descontos_do_pedido(pedido), [
            {'tipo': 'desconto', 'rotulo': 'Desconto', 'valor': '20.00'},
        ])

    def test_payload_da_comanda_leva_as_linhas(self):
        from apps.stores.services.print_service import build_order_print_payload
        pedido = self._pedido(itens=[(self.salmao, 1)], discount='5.29', coupon_code='BEMVINDO10')
        payload = build_order_print_payload(pedido)
        self.assertEqual(payload['totals']['descontos'][0]['rotulo'], 'Cupom BEMVINDO10')

    def test_api_do_pedido_leva_as_linhas(self):
        from apps.stores.api.serializers import StoreOrderSerializer
        pedido = self._pedido(itens=[(self.salmao, 1)], discount='5.29', coupon_code='BEMVINDO10')
        self.assertEqual(StoreOrderSerializer(pedido).data['descontos'][0]['tipo'], 'cupom')
