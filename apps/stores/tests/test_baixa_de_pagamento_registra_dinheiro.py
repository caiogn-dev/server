"""Dar baixa no pagamento tem que registrar o DINHEIRO, não só o rótulo.

O painel marca "Pagamento lançado" com `PATCH {payment_status: 'paid'}`. Isso
gravava só o rótulo no pedido — mas o saldo (`amount_paid`/`amount_due`/
`is_fully_paid`) é DERIVADO das cobranças (`StorePayment` com status
`completed`). Sem criar a cobrança, o rótulo dizia "pago" e o dinheiro dizia
que não entrou.

Resultado medido na Cê Saladas em 09/09/2026: de 52 pedidos já concluídos com
`amount_due > 0`, **51 tinham `payment_status = 'paid'`**. O modal mostrava
"Falta receber R$ 41,32" num pedido entregue, pago em dinheiro e com a baixa
lançada — e o relatório de receita contava menos do que a loja faturou.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class BaixaDePagamentoTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-bx', password='x')
        self.store = Store.objects.create(
            name='Loja BX', slug='loja-bx', owner=self.owner, status='active')
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Dyana', customer_phone='5563984143551',
            status='delivered', payment_status='pending', payment_method='cash',
            subtotal=Decimal('41.32'), total=Decimal('41.32'),
        )
        self.client.force_authenticate(user=self.owner)
        self.url = f'/api/v1/stores/orders/{self.order.id}/'

    def _recarrega(self):
        return StoreOrder.objects.get(pk=self.order.pk)

    def _dar_baixa(self):
        return self.client.patch(self.url, {'payment_status': 'paid'}, format='json')

    # ── o caso do dono ────────────────────────────────────────────────────

    def test_baixa_zera_o_que_falta_receber(self):
        resp = self._dar_baixa()
        assert resp.status_code == 200, resp.content
        pedido = self._recarrega()
        assert pedido.amount_paid == Decimal('41.32')
        assert pedido.amount_due == Decimal('0.00')
        assert pedido.is_fully_paid is True

    def test_baixa_cria_a_cobranca_que_prova_o_recebimento(self):
        self._dar_baixa()
        cobranca = StorePayment.objects.get(order=self.order)
        assert cobranca.status == 'completed'
        assert cobranca.amount == Decimal('41.32')
        # A forma de pagamento é a do PEDIDO: quem recebeu em dinheiro não
        # pode virar "pix" no relatório.
        assert cobranca.payment_method == 'cash'

    def test_a_resposta_do_patch_ja_vem_quitada(self):
        """A tela usa a resposta do PATCH — se ela vier velha, o modal segue
        dizendo 'Falta receber' até alguém recarregar."""
        resp = self._dar_baixa()
        assert Decimal(str(resp.json()['amount_due'])) == Decimal('0.00')
        assert resp.json()['is_fully_paid'] is True

    # ── não pode cobrar duas vezes ────────────────────────────────────────

    def test_dar_baixa_duas_vezes_nao_duplica_o_dinheiro(self):
        self._dar_baixa()
        self._dar_baixa()
        assert StorePayment.objects.filter(order=self.order).count() == 1
        assert self._recarrega().amount_paid == Decimal('41.32')

    def test_com_pagamento_parcial_registra_so_a_diferenca(self):
        """Regra do SERVIÇO, não do endpoint.

        Pelo `PATCH` este caso não se alcança: a primeira cobrança
        `completed` já marca o pedido como pago sozinho (`_sync_with_order`),
        então não sobra transição para a view detectar — e o painel nem
        mostra o botão de lançar pagamento num pedido já rotulado como pago.
        """
        from apps.stores.services.recebimento_manual import registrar_recebimento

        StorePayment.objects.create(
            order=self.order, payment_method='pix', status='completed',
            amount=Decimal('20.00'))
        registrar_recebimento(self._recarrega(), autor=self.owner)
        pedido = self._recarrega()
        assert pedido.amount_paid == Decimal('41.32')
        assert pedido.amount_due == Decimal('0.00')
        nova = StorePayment.objects.filter(order=self.order).exclude(payment_method='pix').get()
        assert nova.amount == Decimal('21.32')

    def test_pedido_ja_quitado_nao_ganha_cobranca_fantasma(self):
        StorePayment.objects.create(
            order=self.order, payment_method='pix', status='completed',
            amount=Decimal('41.32'))
        self._dar_baixa()
        assert StorePayment.objects.filter(order=self.order).count() == 1

    # ── só o que é baixa vira dinheiro ────────────────────────────────────

    def test_editar_outro_campo_nao_registra_pagamento(self):
        resp = self.client.patch(self.url, {'customer_name': 'Dyana C.'}, format='json')
        assert resp.status_code == 200, resp.content
        assert StorePayment.objects.filter(order=self.order).count() == 0

    def test_marcar_como_pendente_nao_registra_pagamento(self):
        self.client.patch(self.url, {'payment_status': 'pending'}, format='json')
        assert StorePayment.objects.filter(order=self.order).count() == 0

    # ── o outro caminho do painel ─────────────────────────────────────────

    def test_o_endpoint_dedicado_tambem_registra(self):
        """`update_payment_status/` é o segundo caminho que marca pago. Se só
        um dos dois registrar o dinheiro, o defeito volta pelo outro."""
        resp = self.client.post(
            f'{self.url}update_payment_status/', {'payment_status': 'paid'}, format='json')
        assert resp.status_code == 200, resp.content
        pedido = self._recarrega()
        assert pedido.amount_due == Decimal('0.00')
        assert StorePayment.objects.filter(order=self.order).count() == 1

