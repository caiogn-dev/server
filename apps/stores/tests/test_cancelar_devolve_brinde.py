"""Cancelar o pedido não devolvia o brinde de fidelidade usado nele.

Irmão de test_cancelar_devolve_saldo_usado.py (17/set, cashback e carteira).
O cliente junta carimbos, troca por uma salada grátis num pedido
(`LoyaltyService.redeem` → REDEEM + `redeemed_count += 1`), a loja cancela o
pedido — e o brinde fica gasto. Ele juntou os carimbos e não comeu nada.

A devolução é uma transação ADJUST ligada ao pedido cancelado: a constraint
`loyalty_unique_order_kind` (order, kind) garante que cancelar duas vezes não
devolve dois brindes.

Fora do escopo DE PROPÓSITO: os carimbos GANHOS num pedido pago e depois
cancelado continuam com o cliente. Isso favorece o cliente e é decisão de
negócio do dono, não defeito.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreLoyaltyAccount, StoreOrder
from apps.stores.services.loyalty_service import LoyaltyService
from apps.stores.services.order_service import order_service

User = get_user_model()


class CancelarDevolveBrindeTests(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-brinde', password='x')
        self.cliente = User.objects.create_user(username='cliente-brinde', password='x')
        self.loja = Store.objects.create(
            name='Loja Brinde', slug='loja-brinde', owner=dono, status='active',
            metadata={'loyalty_salads_required': 5, 'loyalty_enabled': True},
        )
        antigo = self._pedido(status='delivered')
        LoyaltyService.credit_qualified(self.loja, self.cliente, antigo, quantity=5)
        self.pedido = self._pedido(status='confirmed')
        LoyaltyService.redeem(self.loja, self.cliente, self.pedido, rewards=1)

    def _pedido(self, **kw):
        return StoreOrder.objects.create(
            store=self.loja, customer=self.cliente, subtotal=30, total=30, **kw,
        )

    def _resgatados(self):
        return StoreLoyaltyAccount.objects.get(
            store=self.loja, user=self.cliente,
        ).redeemed_count

    def test_brinde_volta_ao_cancelar(self):
        self.assertEqual(self._resgatados(), 1)

        order_service.cancel_order(self.pedido, reason='acabou o salmão')

        self.assertEqual(self._resgatados(), 0)

    def test_cancelar_de_novo_nao_devolve_em_dobro(self):
        order_service.cancel_order(self.pedido, reason='1ª')
        self.pedido.refresh_from_db()
        order_service.update_status(self.pedido, 'cancelled')

        self.assertEqual(self._resgatados(), 0)

    def test_pedido_sem_brinde_nao_mexe_na_conta(self):
        outro = self._pedido(status='confirmed')

        order_service.cancel_order(outro, reason='sem brinde')

        self.assertEqual(self._resgatados(), 1)
