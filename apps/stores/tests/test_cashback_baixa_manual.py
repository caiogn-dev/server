"""Dar BAIXA no cashback usado fora do sistema.

O ajuste manual só sabia creditar. Quando o cliente gasta o saldo por fora —
desconto dado no WhatsApp, no balcão, num pedido lançado à mão — o painel
continuava mostrando o crédito, e a loja pagava o mesmo desconto duas vezes.

`CashbackService.redeem` já consome os lotes por ordem de vencimento; faltava
alguém do lado do painel chamá-lo.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.cashback import StoreCashbackLot, StoreCashbackRedemption

User = get_user_model()


class BaixaManualDeCashbackTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-bm', password='x')
        self.outro = User.objects.create_user(username='intruso-bm', password='x')
        self.store = Store.objects.create(
            name='Loja BM', slug='loja-bm', owner=self.owner, status='active')
        self.url = f'/api/v1/stores/{self.store.slug}/cashback/ajustar/'
        self.phone = '5563999192628'
        StoreCashbackLot.objects.create(
            store=self.store, phone=self.phone, amount=Decimal('10.00'),
            remaining=Decimal('10.00'), expires_at=timezone.now() + timedelta(days=30))
        self.client.force_authenticate(user=self.owner)

    def _saldo(self):
        from apps.stores.services.cashback_service import CashbackService
        return CashbackService.balance(self.store, self.phone, verificado=True)

    def test_valor_negativo_da_baixa_no_saldo(self):
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '-4.00', 'motivo': 'desconto dado no WhatsApp',
        }, format='json')
        assert resp.status_code in (200, 201), resp.content
        assert self._saldo() == Decimal('6.00')

    def test_baixa_vira_resgate_registrado(self):
        self.client.post(self.url, {
            'phone': self.phone, 'valor': '-4.00', 'motivo': 'balcão',
        }, format='json')
        resgate = StoreCashbackRedemption.objects.get(store=self.store)
        assert resgate.amount == Decimal('4.00')

    def test_baixa_maior_que_o_saldo_nao_deixa_negativo(self):
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '-25.00', 'motivo': 'erro de digitação',
        }, format='json')
        assert resp.status_code in (200, 201), resp.content
        assert self._saldo() == Decimal('0.00')

    def test_baixa_sem_motivo_e_recusada(self):
        resp = self.client.post(self.url, {'phone': self.phone, 'valor': '-4.00'}, format='json')
        assert resp.status_code == 400
        assert self._saldo() == Decimal('10.00')

    def test_valor_zero_continua_recusado(self):
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '0', 'motivo': 'nada',
        }, format='json')
        assert resp.status_code == 400

    def test_teto_vale_para_a_baixa_tambem(self):
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '-9000.00', 'motivo': 'zero a mais',
        }, format='json')
        assert resp.status_code == 400
        assert self._saldo() == Decimal('10.00')

    def test_nao_dono_recebe_403(self):
        self.client.force_authenticate(user=self.outro)
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '-4.00', 'motivo': 'x',
        }, format='json')
        assert resp.status_code == 403
        assert self._saldo() == Decimal('10.00')

    def test_credito_continua_funcionando(self):
        resp = self.client.post(self.url, {
            'phone': self.phone, 'valor': '5.00', 'motivo': 'cortesia',
        }, format='json')
        assert resp.status_code == 201, resp.content
        assert self._saldo() == Decimal('15.00')
