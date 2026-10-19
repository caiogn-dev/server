"""Acréscimo digitado ao criar o pedido no painel precisa existir no PEDIDO.

19/10/2026, Ivoneth (IVO2610194941): coffee break de 50 pessoas (R$ 1.695)
ampliado para 60 — R$ 299 das 10 pessoas a mais + R$ 50 de entrega, lançados
como acréscimo de R$ 349. O total foi a R$ 2.044, mas o acréscimo ficou só em
`metadata['manual_surcharge']`; `surcharge_value` ficou 0. A NF-e somou
R$ 1.695 de itens contra R$ 2.044 de pagamento e a SEFAZ recusou:

    Rejeicao: Ausencia de troco quando o valor dos pagamentos informados
    for maior que o total da nota

E qualquer recálculo do pedido apagaria os R$ 349 em silêncio.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.services import build_nfce_payload
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreProduct

User = get_user_model()


class AcrescimoManualNaNotaTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-acrescimo', password='x')
        self.store = Store.objects.create(
            name='Loja Acréscimo', slug='loja-acrescimo', owner=self.owner, status='active',
        )
        categoria = StoreCategory.objects.create(store=self.store, name='Coffee', slug='coffee')
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Coffee Break 50 Pessoas', price=Decimal('1695.00'),
            track_stock=False, category=categoria,
        )
        self.client.force_authenticate(self.owner)

    def _criar(self):
        resp = self.client.post(f'/api/v1/stores/{self.store.slug}/orders/', {
            'store': str(self.store.id),
            'customer_name': 'Sindicato',
            'customer_phone': '5563992243412',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            'surcharge': '349.00',
            'adjustment_reason': '+10 pessoas e entrega',
            'items': [{'product_id': str(self.produto.id), 'quantity': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return StoreOrder.objects.get(order_number=resp.data['order_number'])

    def test_acrescimo_vai_para_surcharge_value(self):
        pedido = self._criar()
        self.assertEqual(pedido.total, Decimal('2044.00'))
        self.assertEqual(pedido.surcharge_value, Decimal('349.00'))
        self.assertEqual(pedido.surcharge_reason, '+10 pessoas e entrega')

    def test_recalcular_nao_apaga_o_acrescimo(self):
        pedido = self._criar()
        pedido.recalculate_totals()
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal('2044.00'))

    def test_nota_fecha_itens_mais_outras_despesas_com_o_pagamento(self):
        pedido = self._criar()
        payload = build_nfce_payload(pedido, {'cnpj': '11222333000181'})
        itens = sum(Decimal(str(i['valor_bruto'])) for i in payload['itens'])
        outras = Decimal(str(payload.get('valor_outras_despesas', 0)))
        pago = sum(Decimal(str(p['valor_pagamento'])) for p in payload['formas_pagamento'])
        self.assertEqual(itens + outras, pago)
