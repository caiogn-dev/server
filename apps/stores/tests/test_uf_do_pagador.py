"""payer.address.state precisa ser a SIGLA de 2 letras.

A Orders API recusa a order INTEIRA com
  400 property_value: '$.payer.address.state' - length must be <= 2, but got 9
quando o endereço traz "Tocantins" em vez de "TO". O pedido da Simone
(CE-2608197996) morreu por isso: mesmo com o valor certo e o frete somando,
o payload inteiro foi rejeitado por causa de um campo de texto.

Vale para PIX e CARTÃO — os dois passam pelo mesmo build_payer.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services import mp_orders


class SiglaDoEstadoTests(TestCase):
    def test_nome_por_extenso_vira_sigla(self):
        self.assertEqual(mp_orders.sigla_do_estado('Tocantins'), 'TO')
        self.assertEqual(mp_orders.sigla_do_estado('São Paulo'), 'SP')
        self.assertEqual(mp_orders.sigla_do_estado('Sao Paulo'), 'SP')
        self.assertEqual(mp_orders.sigla_do_estado('rio de janeiro'), 'RJ')
        self.assertEqual(mp_orders.sigla_do_estado('MINAS GERAIS'), 'MG')

    def test_sigla_continua_sigla(self):
        self.assertEqual(mp_orders.sigla_do_estado('TO'), 'TO')
        self.assertEqual(mp_orders.sigla_do_estado('to'), 'TO')
        self.assertEqual(mp_orders.sigla_do_estado(' sp '), 'SP')

    def test_desconhecido_nao_passa_lixo_de_9_letras(self):
        """Melhor não mandar o campo do que mandar algo que derruba a order."""
        self.assertIsNone(mp_orders.sigla_do_estado('Freedonia'))
        self.assertIsNone(mp_orders.sigla_do_estado(''))
        self.assertIsNone(mp_orders.sigla_do_estado(None))


class EnderecoDoPagadorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_uf', email='d@uf.com', password='x')
        self.store = Store.objects.create(name='Loja UF', slug='loja-uf', owner=owner)

    def _pedido(self, estado):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Simone Paz',
            customer_email='s@t.com', customer_phone='63999990000',
            subtotal=Decimal('30.75'), delivery_fee=Decimal('11.90'),
            total=Decimal('42.65'),
            delivery_address={
                'street_name': 'Quadra 403 Sul Avenida NS 1',
                'street_number': '401', 'city': 'Palmas',
                'state': estado, 'zip_code': '77016524',
            },
        )

    def test_pedido_da_simone_gera_uf_valida(self):
        p = mp_orders.build_pix_order_payload(self._pedido('Tocantins'), 's@t.com')
        self.assertEqual(p['payer']['address']['state'], 'TO')

    def test_cartao_tambem_normaliza(self):
        p = mp_orders.build_order_payload(
            self._pedido('Tocantins'), card_token='t', payment_method_id='visa',
            installments=1, payer_email='s@t.com',
        )
        self.assertEqual(p['payer']['address']['state'], 'TO')

    def test_estado_irreconhecivel_omite_o_campo(self):
        p = mp_orders.build_pix_order_payload(self._pedido('Freedonia'), 's@t.com')
        self.assertNotIn('state', p['payer']['address'])

    def test_nenhum_state_passa_de_2_chars(self):
        for estado in ['Tocantins', 'TO', 'São Paulo', 'Rio Grande do Sul', 'Freedonia']:
            p = mp_orders.build_pix_order_payload(self._pedido(estado), 's@t.com')
            uf = p['payer']['address'].get('state')
            if uf is not None:
                self.assertLessEqual(len(uf), 2, f'{estado} gerou {uf!r}')
