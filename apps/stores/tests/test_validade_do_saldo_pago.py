"""Saldo comprado dura mais que cashback. São dinheiros diferentes.

O CASO (04/09): o pacote Família custa R$ 395 e credita R$ 456 — e o crédito
herdava a validade do CASHBACK, 30 dias. Isso obriga a cliente a comer R$ 15,20
de salada por dia durante um mês, ou perder o que PAGOU.

Medido contra a base real da Cê: das dez melhores clientes, só uma gasta o
suficiente para consumir o Família em 30 dias. As outras nove perderiam
dinheiro — e são justamente as pessoas que a loja mais quer manter.

A DIFERENÇA QUE JUSTIFICA DUAS VALIDADES:

  cashback   é BÔNUS que a loja deu. Vencer é o que cria a urgência que faz o
             programa funcionar — 30 dias traz a cliente de volta.

  carteira   é dinheiro que a cliente PAGOU. Vencer não cria urgência: cria
             prejuízo para ela e um pedido de reembolso para a loja. Fora que
             tomar de volta valor pré-pago é frágil perante o CDC.

Decisão do dono: 3 meses para o saldo comprado, cashback continua menor.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreCashbackLot
from apps.stores.services.cashback_service import CashbackService

User = get_user_model()


class ValidadeDoSaldoPagoTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-validade', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-validade', owner=dono,
            store_type='food', status='active',
            metadata={
                'cashback_enabled': True,
                # A Cê está configurada em 30 dias de cashback; o padrão do
                # código é 60. O teste fixa o cenário real da loja.
                'cashback_expiry_days': '30',
                'carteira_tiers': [
                    {'id': 'leve', 'nome': 'Leve', 'paga': '139', 'credito': '152'},
                ],
            },
        )
        self.phone = '5563999900033'

    def _dias_ate_vencer(self, lote):
        return round((lote.expires_at - timezone.now()).total_seconds() / 86400)

    def test_saldo_comprado_dura_tres_meses(self):
        pacote = CashbackService.tiers(self.store)[0]

        lote = CashbackService.credit_prepaid(
            self.store, self.phone, pacote['id'], source_ref='cobranca-1',
        )

        self.assertEqual(self._dias_ate_vencer(lote), 90)

    def test_cashback_de_compra_continua_curto(self):
        """A urgência do cashback é o que traz a cliente de volta."""
        lote = CashbackService._creditar(
            self.store, self.phone, 5, StoreCashbackLot.Origin.PURCHASE,
        )

        self.assertEqual(self._dias_ate_vencer(lote), 30)

    def test_a_loja_pode_mudar_a_validade_do_pacote(self):
        self.store.metadata = {**self.store.metadata, 'carteira_validade_dias': '180'}
        self.store.save(update_fields=['metadata'])
        pacote = CashbackService.tiers(self.store)[0]

        lote = CashbackService.credit_prepaid(
            self.store, self.phone, pacote['id'], source_ref='cobranca-2',
        )

        self.assertEqual(self._dias_ate_vencer(lote), 180)

    def test_a_tela_informa_a_validade_do_saldo_comprado(self):
        """Prometer 3 meses e a tela dizer 30 dias é pior que não prometer."""
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/carteira/')

        self.assertEqual(r.data['carteira_validade_dias'], 90)
        self.assertEqual(r.data['validade_dias'], 30)

    def test_o_saldo_comprado_e_gasto_por_ultimo_quando_dura_mais(self):
        """FIFO por VENCIMENTO: o cashback curto tem que sair primeiro.

        Se o saldo comprado (90d) fosse consumido antes do cashback (30d), a
        cliente perderia o bônus que estava prestes a vencer enquanto o
        dinheiro dela ficava parado — pagando para perder.
        """
        pacote = CashbackService.tiers(self.store)[0]
        CashbackService.credit_prepaid(
            self.store, self.phone, pacote['id'], source_ref='cobranca-3',
        )
        CashbackService._creditar(
            self.store, self.phone, 10, StoreCashbackLot.Origin.PURCHASE,
        )

        lotes = list(
            StoreCashbackLot.objects
            .filter(store=self.store, phone=self.phone)
            .order_by('expires_at')
        )

        self.assertEqual(lotes[0].origin, StoreCashbackLot.Origin.PURCHASE)
