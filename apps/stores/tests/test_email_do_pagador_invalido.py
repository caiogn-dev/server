"""E-mail inválido vindo do formulário do cartão não pode derrubar a venda.

17/set/2026, pedido CE-2609179077 (Madu, R$ 31,34, cartão Master). A Orders
API recusou com `invalid_payer_email`. O e-mail da conta dela é válido — o
inválido veio do formulário de cartão do site, que tem prioridade sobre o do
pedido (`payer_data.get('email') or payer_email`). Ela leu "O pagamento não foi
autorizado. Tente outro cartão ou pague no PIX" — como se o cartão fosse o
problema — e refez o pedido no PIX. O pedido do cartão ficou para o dono
cancelar à mão.

Duas correções:
1. `build_payer` só aceita um e-mail que o MP aceitaria; senão usa o do pedido.
2. `invalid_payer_email` ganha texto próprio.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services import mp_orders


class EmailDoPagadorTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user('dono-pag', 'dono-pag@x.com', 'x')
        loja = Store.objects.create(name='Loja Pag', slug='loja-pag', owner=dono,
                                    status=Store.StoreStatus.ACTIVE)
        self.pedido = StoreOrder.objects.create(
            store=loja, customer_name='Maria Eduarda',
            customer_email='madu@gmail.com', customer_phone='+55 63 99243-3905',
            subtotal=Decimal('31.34'), total=Decimal('31.34'),
        )

    def _email(self, do_formulario):
        return mp_orders.build_payer(self.pedido, do_formulario, {})['email']

    def test_email_malformado_do_formulario_cai_no_do_pedido(self):
        self.assertEqual(self._email('madu@gmail'), 'madu@gmail.com')

    def test_email_com_espaco_do_formulario_cai_no_do_pedido(self):
        self.assertEqual(self._email('maria eduarda@gmail.com'), 'madu@gmail.com')

    def test_placeholder_interno_cai_no_do_pedido(self):
        self.assertEqual(self._email('5563992433905@pastita.local'), 'madu@gmail.com')

    def test_email_vazio_usa_o_do_pedido(self):
        self.assertEqual(self._email(''), 'madu@gmail.com')

    def test_email_valido_do_formulario_e_respeitado(self):
        """Âncora: quem digitou outro e-mail válido no cartão continua valendo."""
        self.assertEqual(self._email('outro@hotmail.com'), 'outro@hotmail.com')

    def test_email_com_espacos_nas_pontas_e_limpo(self):
        self.assertEqual(self._email('  outro@hotmail.com '), 'outro@hotmail.com')


class MensagemDoEmailInvalidoTest(TestCase):
    def test_invalid_payer_email_fala_de_email_e_nao_de_cartao(self):
        msg = mp_orders.mensagem_de_recusa('invalid_payer_email')
        self.assertIn('e-mail', msg.lower())
        self.assertNotEqual(msg, mp_orders.RECUSA_GENERICA)
