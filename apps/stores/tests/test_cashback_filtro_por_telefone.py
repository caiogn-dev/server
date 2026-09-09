"""O filtro `?phone=` da tela de cashback precisa achar o cliente do jeito que
o telefone dele está gravado.

A ficha do cliente busca o saldo por `whatsapp || phone`. O filtro comparava
por igualdade com `normalize_phone_number`, que ACRESCENTA o nono dígito — mas
o lote pode ter sido gravado sem ele. Medido em produção (09/09/2026): a
cliente 5563984573670 tem lote sob '556384573670' e a ficha mostrava saldo
zero. 1 dos 7 clientes com saldo da Cê Saladas era invisível.

`LoyaltyGuestStatusView._build_phone_variants` já resolvia isso do outro lado
do sistema; aqui a peneira não existia.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.cashback import StoreCashbackLot

User = get_user_model()


class CashbackFiltroPorTelefoneTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-cf', password='x')
        self.store = Store.objects.create(
            name='Loja CF', slug='loja-cf', owner=self.owner, status='active')
        self.url = f'/api/v1/stores/{self.store.slug}/cashback/'
        self.client.force_authenticate(user=self.owner)

    def _lote(self, phone, valor='5.00'):
        return StoreCashbackLot.objects.create(
            store=self.store, phone=phone, amount=Decimal(valor),
            remaining=Decimal(valor), expires_at=timezone.now() + timedelta(days=30),
        )

    def _saldos(self, phone):
        resp = self.client.get(self.url, {'phone': phone})
        assert resp.status_code == 200, resp.content
        return resp.json()['results']

    @staticmethod
    def _saldo(linha):
        """O saldo chega como número no JSON — comparar como Decimal evita
        depender da grafia ('5.0' vs '5.00')."""
        return Decimal(str(linha['saldo']))

    def test_acha_o_lote_gravado_sem_o_nono_digito(self):
        self._lote('556384573670')
        assert self._saldo(self._saldos('556384573670')[0]) == Decimal('5.00')

    def test_acha_pelo_numero_com_nove_o_lote_gravado_sem_nove(self):
        """O caso real: o cadastro tem o 9, o lote não."""
        self._lote('556384573670')
        assert self._saldo(self._saldos('5563984573670')[0]) == Decimal('5.00')

    def test_acha_pelo_numero_sem_nove_o_lote_gravado_com_nove(self):
        self._lote('5563984573670')
        assert self._saldo(self._saldos('556384573670')[0]) == Decimal('5.00')

    def test_soma_as_duas_grafias_do_mesmo_cliente(self):
        """Dois lotes, duas grafias, uma pessoa — a ficha não pode mostrar metade."""
        self._lote('556384573670', '3.00')
        self._lote('5563984573670', '4.00')
        linhas = self._saldos('5563984573670')
        assert len(linhas) == 1, linhas
        assert self._saldo(linhas[0]) == Decimal('7.00')

    def test_nao_confunde_clientes_diferentes(self):
        self._lote('5563984573670', '5.00')
        assert self._saldos('5563999192628') == []
