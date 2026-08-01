"""Caixa (PDV): abertura, sangria/reforço e fechamento com conferência."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCashSession

User = get_user_model()


class CashSessionTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-cash', email='owner-cash@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Cash', slug='loja-cash', owner=self.owner, status='active',
        )
        self.client.force_authenticate(self.owner)
        self.base = f'/api/v1/stores/{self.store.slug}/cash'

    def _open(self, amount='100.00'):
        return self.client.post(f'{self.base}/open/', {'opening_amount': amount}, format='json')

    def test_abre_caixa_com_fundo_de_troco(self):
        resp = self._open('150.00')
        self.assertEqual(resp.status_code, 201, resp.content)
        session = StoreCashSession.objects.get(store=self.store)
        self.assertEqual(session.opening_amount, Decimal('150.00'))
        self.assertEqual(session.status, 'open')
        self.assertEqual(session.opened_by, self.owner)

    def test_nao_abre_segundo_caixa_na_mesma_loja(self):
        self._open()
        resp = self._open()
        self.assertEqual(resp.status_code, 409)

    def test_current_retorna_caixa_aberto(self):
        self._open('50.00')
        resp = self.client.get(f'{self.base}/current/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'open')
        self.assertEqual(Decimal(resp.data['opening_amount']), Decimal('50.00'))

    def test_current_sem_caixa_aberto_404(self):
        resp = self.client.get(f'{self.base}/current/')
        self.assertEqual(resp.status_code, 404)

    def test_sangria_e_reforco(self):
        self._open('100.00')
        out = self.client.post(f'{self.base}/movement/', {
            'kind': 'sangria', 'amount': '40.00', 'reason': 'Depósito banco',
        }, format='json')
        self.assertEqual(out.status_code, 201, out.content)
        rein = self.client.post(f'{self.base}/movement/', {
            'kind': 'reforco', 'amount': '20.00', 'reason': 'Troco extra',
        }, format='json')
        self.assertEqual(rein.status_code, 201)

        session = StoreCashSession.objects.get(store=self.store)
        # esperado em caixa = 100 - 40 + 20 = 80
        self.assertEqual(session.expected_cash(), Decimal('80.00'))

    def test_movimento_sem_caixa_aberto_400(self):
        resp = self.client.post(f'{self.base}/movement/', {
            'kind': 'sangria', 'amount': '10.00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_fechamento_calcula_diferenca(self):
        self._open('100.00')
        self.client.post(f'{self.base}/movement/', {'kind': 'sangria', 'amount': '40.00'}, format='json')
        resp = self.client.post(f'{self.base}/close/', {'counted_amount': '75.00'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        session = StoreCashSession.objects.get(store=self.store)
        self.assertEqual(session.status, 'closed')
        self.assertEqual(session.counted_amount, Decimal('75.00'))
        # esperado 60 (100-40) → diferença -... espera: 100-40=60; contado 75 → +15
        self.assertEqual(session.difference, Decimal('15.00'))
        self.assertIsNotNone(session.closed_at)

    def test_expected_cash_soma_vendas_em_dinheiro_da_sessao(self):
        from django.utils import timezone
        from datetime import timedelta
        from apps.stores.models import StoreOrder

        self._open('100.00')
        session = StoreCashSession.objects.get(store=self.store)

        def cash_order(tag, total, paid_at, method='cash', paid=True):
            o = StoreOrder.objects.create(
                store=self.store, customer_name='C', customer_phone=f'55639{tag}',
                subtotal=Decimal(total), total=Decimal(total),
                payment_method=method,
                payment_status='paid' if paid else 'pending',
                status='completed',
            )
            StoreOrder.objects.filter(pk=o.pk).update(paid_at=paid_at)
            return o

        now = timezone.now()
        cash_order('1', '50.00', now)                                  # dinheiro, na sessão → conta
        cash_order('2', '30.00', now, method='pix')                    # pix → não conta
        cash_order('3', '20.00', now, paid=False)                      # dinheiro não pago → não conta
        cash_order('4', '25.00', now - timedelta(hours=1))             # pago ANTES de abrir → não conta

        # 100 (fundo) + 50 (venda em dinheiro) = 150
        self.assertEqual(session.expected_cash(), Decimal('150.00'))

    def test_fechar_sem_caixa_aberto_400(self):
        resp = self.client.post(f'{self.base}/close/', {'counted_amount': '10.00'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_exige_autenticacao(self):
        self.client.force_authenticate(None)
        self.assertIn(self._open().status_code, (401, 403))
