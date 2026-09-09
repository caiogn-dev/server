"""Loja com entrega desligada não aceita pedido de entrega.

`delivery_enabled` / `pickup_enabled` existiam no `Store`, a API os expunha e o
cardápio já os respeitava (`DeliveryBar.jsx`) — mas NADA validava no checkout.
Esconder o botão no cardápio não fecha a porta: o bot do WhatsApp, o PDV e
qualquer POST direto continuavam criando pedido de entrega numa loja que só
faz retirada.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StoreProduct

User = get_user_model()


class ModoDesligadoTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-md', password='x')
        self.store = Store.objects.create(
            name='Só Retirada', slug='so-retirada', owner=self.owner, status='active',
            delivery_enabled=False, pickup_enabled=True,
        )
        # `track_stock=False`: o assunto aqui é o modo de recebimento, não o
        # estoque — sem isso o pedido morre antes de chegar na regra testada.
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Lasanha congelada', price=Decimal('30.00'),
            track_stock=False)
        self.client.force_authenticate(user=self.owner)

    def _cria(self, metodo):
        return self.client.post(
            '/api/v1/stores/orders/',
            {
                'store': str(self.store.id),
                'customer_name': 'Cliente',
                'customer_phone': '5563999999999',
                'delivery_method': metodo,
                'subtotal': '30.00',
                'total': '30.00',
                'items': [{
                    'product_id': str(self.produto.id),
                    'quantity': 1,
                    'unit_price': '30.00',
                    'subtotal': '30.00',
                }],
            },
            format='json',
        )

    def test_entrega_desligada_recusa_pedido_de_entrega(self):
        resp = self._cria('delivery')
        assert resp.status_code == 400, resp.content
        assert 'entrega' in str(resp.content, 'utf-8').lower()
        assert StoreOrder.objects.filter(store=self.store).count() == 0

    def test_retirada_continua_passando(self):
        resp = self._cria('pickup')
        assert resp.status_code in (200, 201), resp.content

    def test_loja_com_os_dois_ligados_aceita_entrega(self):
        self.store.delivery_enabled = True
        self.store.save(update_fields=['delivery_enabled'])
        assert self._cria('delivery').status_code in (200, 201)

    def test_retirada_desligada_recusa_pedido_de_retirada(self):
        self.store.delivery_enabled = True
        self.store.pickup_enabled = False
        self.store.save(update_fields=['delivery_enabled', 'pickup_enabled'])
        resp = self._cria('pickup')
        assert resp.status_code == 400, resp.content

    def test_link_de_pagamento_nao_e_barrado(self):
        """`digital` não é entrega nem retirada — é cobrança avulsa. Barrá-lo
        junto mataria a venda por link numa loja só de retirada."""
        assert self._cria('digital').status_code in (200, 201)
