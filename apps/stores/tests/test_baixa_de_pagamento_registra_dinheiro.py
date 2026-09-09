"""Pedido marcado como pago não pode dizer "Falta receber".

O painel marca "Pagamento lançado" e o pedido ganha `payment_status='paid'`.
Esse rótulo É a fonte da verdade do dinheiro em todo o sistema:

    apps/stores/metrics/definicoes.py  →  receita = payment_status='paid'
    apps/stores/models/cash.py         →  gaveta  = payment_method='cash' pago

Nenhum dos dois lê `StorePayment`. Ou seja: o pedido pago em dinheiro JÁ conta
no faturamento, nos relatórios e no caixa.

Só que `amount_due` era derivado exclusivamente das cobranças — e dinheiro na
mão não gera cobrança. Resultado: o modal anunciava "Falta receber R$ 41,32"
num pedido entregue, pago e já faturado. Medido em 09/09/2026: 91 pedidos em 5
lojas, R$ 9.243,79, todos com o rótulo `paid`.

O sintoma era só de EXIBIÇÃO. Por isso a correção é o saldo respeitar o rótulo
— e não criar cobranças que nunca existiram, que seria montar um segundo
livro-caixa ao lado do que o sistema já usa.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class SaldoRespeitaORotuloTest(APITestCase):
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

    # ── o caso do dono ────────────────────────────────────────────────────

    def test_pago_em_dinheiro_nao_fica_devendo(self):
        """Dinheiro na mão não gera cobrança — e nem por isso o pedido deve."""
        self.order.payment_status = 'paid'
        self.order.save(update_fields=['payment_status'])
        pedido = self._recarrega()
        assert pedido.amount_due == Decimal('0.00')
        assert pedido.is_fully_paid is True

    def test_a_resposta_do_patch_ja_vem_quitada(self):
        """A tela usa a resposta do PATCH — se vier velha, o modal segue
        dizendo 'Falta receber' até alguém recarregar."""
        resp = self.client.patch(self.url, {'payment_status': 'paid'}, format='json')
        assert resp.status_code == 200, resp.content
        assert Decimal(str(resp.json()['amount_due'])) == Decimal('0.00')
        assert resp.json()['is_fully_paid'] is True

    def test_nao_inventa_cobranca(self):
        """O faturamento já conta este pedido pelo rótulo. Criar um
        `StorePayment` aqui seria um segundo livro-caixa."""
        self.client.patch(self.url, {'payment_status': 'paid'}, format='json')
        assert StorePayment.objects.filter(order=self.order).count() == 0

    def test_amount_paid_continua_dizendo_a_verdade(self):
        """`amount_paid` é o dinheiro que passou por cobrança. Ele não mente
        para fechar a conta — quem responde "está pago?" é o rótulo."""
        self.order.payment_status = 'paid'
        self.order.save(update_fields=['payment_status'])
        assert self._recarrega().amount_paid == Decimal('0.00')

    # ── o que NÃO pode virar quitado ──────────────────────────────────────

    def test_pendente_continua_devendo_o_total(self):
        pedido = self._recarrega()
        assert pedido.amount_due == Decimal('41.32')
        assert pedido.is_fully_paid is False

    def test_cancelado_nao_vira_quitado(self):
        self.order.payment_status = 'cancelled'
        self.order.save(update_fields=['payment_status'])
        assert self._recarrega().amount_due == Decimal('41.32')

    def test_estornado_nao_vira_quitado(self):
        self.order.payment_status = 'refunded'
        self.order.save(update_fields=['payment_status'])
        assert self._recarrega().amount_due == Decimal('41.32')

    # ── o caminho das cobranças de verdade segue valendo ──────────────────

    def test_cobranca_pendente_ainda_mostra_a_diferenca(self):
        """Enquanto o rótulo não é `paid`, o saldo continua saindo das
        cobranças — é assim que o PIX parcial pede o resto."""
        StorePayment.objects.create(
            order=self.order, payment_method='pix', status='pending',
            amount=Decimal('20.00'))
        assert self._recarrega().amount_due == Decimal('41.32')

    def test_cobranca_quitada_zera_pelo_caminho_de_sempre(self):
        """`_sync_with_order` marca o pedido como pago na 1ª cobrança
        `completed`, então o saldo zera pelos dois caminhos — mesmo fim."""
        StorePayment.objects.create(
            order=self.order, payment_method='pix', status='completed',
            amount=Decimal('41.32'))
        assert self._recarrega().amount_due == Decimal('0.00')

    def test_rotulo_nao_apaga_diferenca_de_cobranca_parcial(self):
        """`_sync_with_order` marca `paid` já na PRIMEIRA cobrança quitada,
        mesmo parcial. Se o rótulo zerasse o saldo aqui, o dono perderia o
        "cobrar a diferença" — que é justamente o caso do PIX pela metade.

        Por isso o rótulo só quita quando NÃO houve cobrança nenhuma: aí o
        dinheiro veio por fora e não há nada mais fino para consultar.
        """
        StorePayment.objects.create(
            order=self.order, payment_method='pix', status='completed',
            amount=Decimal('20.00'))
        pedido = self._recarrega()
        assert pedido.payment_status == 'paid'      # o sync rotulou
        assert pedido.amount_paid == Decimal('20.00')
        assert pedido.amount_due == Decimal('21.32')   # e ainda falta
        assert pedido.is_fully_paid is False
