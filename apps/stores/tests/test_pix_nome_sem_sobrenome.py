"""Cliente que digita só o primeiro nome não pode perder o PIX.

Em 31/08 a Cê Saladas parou de gerar PIX para quem se identificava como "Ana"
ou "Paulo": a Orders API recusava o pedido inteiro com

    400 property_value — '$.payer.last_name' - length must be >= 1, but got 0

O `split_name` devolvia sobrenome vazio e o payload ia com `last_name: ''`.
Como PIX recusado cai no link de pagamento (fallback de 19/08), o cliente era
jogado no checkout do Mercado Pago em vez de receber o copia-e-cola — em
silêncio, sem ninguém perceber que o PIX tinha morrido.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services import mp_orders


class NomeSemSobrenomeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_ns', email='dono@ns.com', password='x')
        self.store = Store.objects.create(name='Loja NS', slug='loja-ns', owner=owner)

    def _pedido(self, nome):
        return StoreOrder.objects.create(
            store=self.store,
            customer_name=nome,
            customer_email='cliente@teste.com',
            customer_phone='63999990000',
            subtotal=Decimal('39.33'),
            total=Decimal('39.33'),
        )

    def test_split_name_nunca_devolve_sobrenome_vazio(self):
        self.assertEqual(mp_orders.split_name('Ana'), ('Ana', 'Ana'))

    def test_split_name_preserva_sobrenome_real(self):
        self.assertEqual(mp_orders.split_name('Maria Silva Souza'), ('Maria', 'Silva Souza'))

    def test_split_name_sem_nome_algum(self):
        primeiro, ultimo = mp_orders.split_name('')
        self.assertTrue(primeiro)
        self.assertTrue(ultimo)

    def test_payer_do_pix_tem_last_name_preenchido(self):
        payload = mp_orders.build_pix_order_payload(self._pedido('Ana'), 'ana@teste.com')
        self.assertTrue(payload['payer']['last_name'])

    def test_payer_do_cartao_tem_last_name_preenchido(self):
        payer = mp_orders.build_payer(self._pedido('Paulo'), 'paulo@teste.com')
        self.assertTrue(payer['last_name'])

    def test_preference_tem_surname_preenchido(self):
        payer = mp_orders.build_preference_payer(self._pedido('Ana'), 'ana@teste.com')
        self.assertTrue(payer['surname'])
