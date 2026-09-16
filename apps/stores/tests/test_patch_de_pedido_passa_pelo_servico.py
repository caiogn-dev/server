"""PATCH no pedido não muda status nem pagamento por fora das regras.

`StoreOrderUpdateSerializer` aceitava `status` e `payment_status` e gravava o
campo cru: sem validar transição, sem liquidar pagamento/cupom/estoque ao
cancelar, sem trava de PIX vencido nem crédito de fidelidade ao pagar. O
painel usava isso no "marcar como pago" (corrigido em 665a3e3).

Regra: `status` por PATCH vai para `OrderService.update_status`; pagamento só
pelos endpoints dedicados (`mark_paid/`, `update_payment_status/`).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class TestPatchDePedidoPassaPeloServico(APITestCase):

    def setUp(self):
        self.dono = User.objects.create_user(username='dono_patch_status', password='x')
        self.loja = Store.objects.create(owner=self.dono, name='Loja Patch', slug='loja-patch-status', status='active')
        self.pedido = StoreOrder.objects.create(
            store=self.loja, total=Decimal('30'), subtotal=Decimal('30'),
            status='delivered', payment_status='paid', payment_method='cash',
        )
        self.client.force_authenticate(self.dono)
        self.url = f'/api/v1/stores/{self.loja.slug}/orders/{self.pedido.id}/'

    def test_transicao_invalida_e_recusada(self):
        resp = self.client.patch(self.url, {'status': 'pending'}, format='json')

        self.assertEqual(resp.status_code, 400, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'delivered')

    def test_cancelar_por_patch_liquida_o_pagamento(self):
        self.pedido.status = 'confirmed'
        self.pedido.save(update_fields=['status'])

        resp = self.client.patch(self.url, {'status': 'cancelled'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'cancelled')
        self.assertEqual(self.pedido.payment_status, 'cancelled')

    def test_pagamento_por_patch_e_recusado(self):
        self.pedido.payment_status = 'pending'
        self.pedido.save(update_fields=['payment_status'])

        resp = self.client.patch(self.url, {'payment_status': 'paid'}, format='json')

        self.assertEqual(resp.status_code, 400, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.payment_status, 'pending')

    def test_editar_dados_continua_funcionando(self):
        resp = self.client.patch(self.url, {'customer_notes': 'sem cebola'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.customer_notes, 'sem cebola')
