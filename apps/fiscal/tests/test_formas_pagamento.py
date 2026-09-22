"""Forma de pagamento na nota — cada método que o sistema aceita.

O mapa conhecia só cash/pix/credit_card/debit_card. `card`, `link`, `voucher`
e `other` caíam em 99 ("Outros") SEM `descricao_pagamento`, que a SEFAZ exige
quando tPag = 99. E cartão (03/04) ia sem o grupo do cartão: a maquininha da
loja não é integrada ao sistema, então `tipo_integracao` = 2 (não integrado),
que dispensa credenciadora e autorização.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.fiscal.services import build_nfce_payload, get_fiscal_config
from apps.stores.models import Store, StoreOrder

User = get_user_model()


class FormasDePagamentoTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='owner-pag', email='pag@test.com', password='x')
        self.store = Store.objects.create(
            name='Loja Pag', slug='loja-pag', owner=owner, status='active',
            metadata={'fiscal': {
                'provider': 'focus', 'cnpj': '11444777000161', 'habilitado': True,
                'inscricao_estadual': '295724145',
            }},
        )

    def _pagamento(self, metodo):
        order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='63999990000',
            subtotal=Decimal('50.00'), total=Decimal('50.00'),
            payment_method=metodo, delivery_method='pickup',
            status='confirmed', payment_status='paid',
        )
        return build_nfce_payload(order, get_fiscal_config(self.store))['formas_pagamento'][0]

    def test_cartao_leva_grupo_nao_integrado(self):
        for metodo, codigo in (('credit_card', '03'), ('debit_card', '04')):
            with self.subTest(metodo=metodo):
                pag = self._pagamento(metodo)
                self.assertEqual(pag['forma_pagamento'], codigo)
                self.assertEqual(pag['tipo_integracao'], 2)

    def test_dinheiro_e_pix_nao_levam_grupo_de_cartao(self):
        for metodo, codigo in (('cash', '01'), ('pix', '17')):
            with self.subTest(metodo=metodo):
                pag = self._pagamento(metodo)
                self.assertEqual(pag['forma_pagamento'], codigo)
                self.assertNotIn('tipo_integracao', pag)

    def test_todo_99_tem_descricao(self):
        for metodo in ('card', 'link', 'voucher', 'voucher_link', 'other', ''):
            with self.subTest(metodo=metodo):
                pag = self._pagamento(metodo)
                self.assertEqual(pag['forma_pagamento'], '99')
                self.assertTrue(2 <= len(pag['descricao_pagamento']) <= 60)
