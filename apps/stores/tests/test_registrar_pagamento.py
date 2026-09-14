"""Registrar pagamento recebido fora do sistema (dinheiro, maquininha, PIX direto).

Antes só existia o "Pagamento lançado" (PATCH payment_status=paid): tudo ou
nada, sem valor, sem método, sem dizer quem deu a baixa. Pedido pago metade em
PIX e metade em dinheiro não tinha como fechar — ficava "Falta receber" para
sempre.

Regras de dinheiro que este registro NÃO pode violar:
- a receita lê `payment_status` (metrics/definicoes.py). O registro vira uma
  cobrança `completed` sem gateway; o rótulo segue a mesma trava do webhook:
  só vira `paid` quando o recebido cobre o total.
- `paid_at` nunca é reescrito.
- duplo clique não registra duas vezes.
- fica dito quem registrou e quando.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class RegistrarPagamentoTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-rp', password='x')
        self.store = Store.objects.create(
            name='Loja RP', slug='loja-rp', owner=self.owner, status='active')
        self.client.force_authenticate(user=self.owner)

    def _pedido(self, total='80.00', payment_status='pending', method='cash', status='delivered', **kw):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5563999990000',
            status=status, payment_status=payment_status, payment_method=method,
            subtotal=Decimal(total), total=Decimal(total), **kw,
        )

    def _cobranca(self, pedido, valor, metodo='pix'):
        return StorePayment.objects.create(
            order=pedido, store=self.store, amount=Decimal(valor),
            payment_method=metodo, status=StorePayment.PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

    def _url(self, pedido, slug=False):
        if slug:
            return f'/api/v1/stores/{self.store.slug}/orders/{pedido.id}/registrar-pagamento/'
        return f'/api/v1/stores/orders/{pedido.id}/registrar-pagamento/'

    def _post(self, pedido, body, slug=False):
        return self.client.post(self._url(pedido, slug), body, format='json')

    # ── o caso do dono ────────────────────────────────────────────────────

    def test_sem_valor_registra_o_que_falta_e_quita(self):
        pedido = self._pedido('80.00')
        resp = self._post(pedido, {'payment_method': 'cash'})
        assert resp.status_code == 201, resp.content
        corpo = resp.json()
        assert corpo['order']['payment_status'] == 'paid'
        assert Decimal(str(corpo['order']['amount_due'])) == Decimal('0.00')
        assert Decimal(str(corpo['order']['amount_paid'])) == Decimal('80.00')
        pedido.refresh_from_db()
        assert pedido.paid_at is not None

    def test_rota_com_slug_da_loja_tambem_funciona(self):
        pedido = self._pedido('30.00')
        resp = self._post(pedido, {'payment_method': 'debit_card'}, slug=True)
        assert resp.status_code == 201, resp.content

    def test_entra_na_receita_uma_vez_so(self):
        pedido = self._pedido('80.00')
        self._post(pedido, {'payment_method': 'cash'})
        receita = metrics.pedidos_de_receita(loja=self.store)
        assert list(receita.values_list('id', flat=True)) == [pedido.id]

    def test_registro_fica_auditavel(self):
        pedido = self._pedido('80.00')
        self._post(pedido, {'payment_method': 'credit_card', 'observacao': 'maquininha Stone'})
        cobranca = StorePayment.objects.get(order=pedido)
        assert cobranca.status == 'completed'
        assert cobranca.gateway_id is None
        assert cobranca.payment_method == 'credit_card'
        assert cobranca.amount == Decimal('80.00')
        assert cobranca.fee == Decimal('0')
        registro = cobranca.metadata['registro_manual']
        assert registro['user_id'] == str(self.owner.id)
        assert registro['registrado_em']
        assert registro['observacao'] == 'maquininha Stone'

    def test_pedido_pix_pago_em_dinheiro_vira_dinheiro_para_a_gaveta(self):
        """A gaveta conta `payment_method='cash'` do pedido: se o PIX nunca
        caiu e o cliente pagou em espécie, o dinheiro está na gaveta."""
        pedido = self._pedido('50.00', method='pix')
        self._post(pedido, {'payment_method': 'cash'})
        pedido.refresh_from_db()
        assert pedido.payment_method == 'cash'

    def test_metodo_misto_nao_reescreve_o_metodo_do_pedido(self):
        pedido = self._pedido('100.00', method='pix', payment_status='processing')
        self._cobranca(pedido, '30.00', 'pix')
        pedido.payment_status = 'processing'
        pedido.paid_at = None
        pedido.save(update_fields=['payment_status', 'paid_at'])
        self._post(pedido, {'payment_method': 'cash'})
        pedido.refresh_from_db()
        assert pedido.payment_method == 'pix'
        assert pedido.payment_status == 'paid'
        assert pedido.amount_paid == Decimal('100.00')

    # ── parcial ───────────────────────────────────────────────────────────

    def test_valor_parcial_nao_marca_pago(self):
        """A trava de parcial do webhook vale aqui também."""
        pedido = self._pedido('80.00')
        resp = self._post(pedido, {'payment_method': 'cash', 'amount': '30.00'})
        assert resp.status_code == 201, resp.content
        pedido.refresh_from_db()
        assert pedido.payment_status == 'processing'
        assert pedido.paid_at is None
        assert pedido.amount_due == Decimal('50.00')
        assert not metrics.pedidos_de_receita(loja=self.store).exists()

    def test_parcial_nunca_rebaixa_pedido_ja_pago(self):
        """Pedido já `paid` pelo rótulo com cobrança a menor (há 3 em produção):
        registrar parte do resto não pode tirá-lo da receita."""
        pedido = self._pedido('100.00', payment_status='paid', method='pix')
        self._cobranca(pedido, '60.00')
        pedido.refresh_from_db()
        paid_at = pedido.paid_at
        resp = self._post(pedido, {'payment_method': 'cash', 'amount': '10.00'})
        assert resp.status_code == 201, resp.content
        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'
        assert pedido.paid_at == paid_at
        assert pedido.amount_due == Decimal('30.00')

    def test_completar_nao_reescreve_paid_at(self):
        pedido = self._pedido('100.00', payment_status='paid', method='pix')
        self._cobranca(pedido, '60.00')
        pedido.refresh_from_db()
        paid_at = pedido.paid_at
        assert paid_at is not None
        self._post(pedido, {'payment_method': 'cash'})
        pedido.refresh_from_db()
        assert pedido.paid_at == paid_at
        assert pedido.amount_due == Decimal('0.00')

    # ── o que precisa ser recusado ────────────────────────────────────────

    def test_pedido_quitado_recusa(self):
        pedido = self._pedido('80.00', payment_status='paid')
        resp = self._post(pedido, {'payment_method': 'cash'})
        assert resp.status_code == 400, resp.content
        assert resp.json()['code'] == 'ja_quitado'
        assert StorePayment.objects.count() == 0

    def test_duplo_clique_sem_chave_nao_registra_duas_vezes(self):
        pedido = self._pedido('80.00')
        self._post(pedido, {'payment_method': 'cash'})
        resp = self._post(pedido, {'payment_method': 'cash'})
        assert resp.status_code == 400
        assert StorePayment.objects.filter(order=pedido).count() == 1

    def test_duplo_clique_com_chave_devolve_o_mesmo_registro(self):
        pedido = self._pedido('80.00')
        body = {'payment_method': 'cash', 'amount': '20.00', 'idempotency_key': 'clique-1'}
        r1 = self._post(pedido, body)
        r2 = self._post(pedido, body)
        assert r1.status_code == 201, r1.content
        assert r2.status_code == 200, r2.content
        assert r1.json()['payment']['id'] == r2.json()['payment']['id']
        assert StorePayment.objects.filter(order=pedido).count() == 1

    def test_valor_acima_do_que_falta_recusa(self):
        pedido = self._pedido('80.00')
        resp = self._post(pedido, {'payment_method': 'cash', 'amount': '100.00'})
        assert resp.status_code == 400
        assert resp.json()['code'] == 'valor_acima_do_saldo'

    def test_valor_zero_ou_negativo_recusa(self):
        pedido = self._pedido('80.00')
        for valor in ('0', '-5', 'abc'):
            resp = self._post(pedido, {'payment_method': 'cash', 'amount': valor})
            assert resp.status_code == 400, valor
        assert StorePayment.objects.count() == 0

    def test_metodo_fora_do_vocabulario_recusa(self):
        """`payment_method` já teve 6 dialetos. Só entram slugs canônicos."""
        pedido = self._pedido('80.00')
        for metodo in ('Dinheiro', 'card', 'link', ''):
            resp = self._post(pedido, {'payment_method': metodo})
            assert resp.status_code == 400, metodo
        assert StorePayment.objects.count() == 0

    def test_pedido_cancelado_recusa(self):
        pedido = self._pedido('80.00', status='cancelled', payment_status='cancelled')
        resp = self._post(pedido, {'payment_method': 'cash'})
        assert resp.status_code == 400
        assert StorePayment.objects.count() == 0

    def test_loja_alheia_nao_enxerga(self):
        outro = User.objects.create_user(username='intruso-rp', password='x')
        Store.objects.create(name='Outra', slug='outra-rp', owner=outro, status='active')
        pedido = self._pedido('80.00')
        self.client.force_authenticate(user=outro)
        resp = self._post(pedido, {'payment_method': 'cash'})
        assert resp.status_code in (403, 404)
        assert StorePayment.objects.count() == 0

    # ── tempo real ────────────────────────────────────────────────────────

    def test_quitar_avisa_o_painel_como_pago(self):
        pedido = self._pedido('80.00')
        with patch('apps.stores.api.views.order_views.broadcast_order_event') as avisar:
            with self.captureOnCommitCallbacks(execute=True):
                self._post(pedido, {'payment_method': 'cash'})
        tipos = [c.kwargs.get('event_type') for c in avisar.call_args_list]
        assert 'order.paid' in tipos
