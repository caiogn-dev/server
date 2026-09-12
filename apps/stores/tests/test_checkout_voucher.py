"""Cobranca de vale no checkout.

Segue o padrao da suite: APITestCase com objetos criados no setUp. Nao existem
fixtures `store_factory`/`order_factory` neste repo.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment, StorePaymentGateway
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.voucher.base import ResultadoDaCobranca

User = get_user_model()

DADOS = {
    'card_token': 'tok_1', 'brand': 'vr',
    'holder_name': 'ANA SILVA', 'holder_document': '39053344705',
}

COBRAR = 'apps.stores.services.voucher.pagarme.PagarmeVoucherProvider.cobrar'


def aprovado():
    return ResultadoDaCobranca(True, 'approved', 'or_9', '', {'id': 'or_9'})


def recusado():
    return ResultadoDaCobranca(False, 'failed', 'or_9', 'Sem saldo.', {'id': 'or_9'})


def pendente():
    return ResultadoDaCobranca(False, 'pending', 'or_9', '', {'id': 'or_9'})


class VoucherNoCheckoutTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-vch', password='x', email='owner-vch@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Vale', slug='loja-vale', owner=self.owner, status='active',
        )
        self.gateway = StorePaymentGateway.objects.create(
            store=self.store, name='Pagar.me', gateway_type='pagarme',
            api_key='sk_test_x', public_key='pk_test_y', is_enabled=True,
            is_sandbox=True, configuration={'voucher_brands': ['vr']},
        )

    def _order(self, total='25.00', store=None):
        return StoreOrder.objects.create(
            store=store or self.store, customer_name='Cliente',
            customer_phone='5599999999999', customer_email='cli@real.com',
            subtotal=Decimal(total), total=Decimal(total),
        )

    def test_a_cobranca_e_registrada_antes_da_chamada(self):
        """Em 31/ago o link de cartao foi o unico caminho SEM StorePayment, e por
        isso o dinheiro sumiu. Aqui a linha nasce antes da rede."""
        order = self._order()
        visto = {}

        def espiar(self_provider, pedido, dados, total=None):
            visto['existia'] = StorePayment.objects.filter(order=pedido).exists()
            return aprovado()

        with patch(COBRAR, espiar):
            CheckoutService.create_payment(order, 'voucher', DADOS)

        self.assertTrue(visto['existia'])

    def test_aprovado_marca_pagamento_e_pedido(self):
        order = self._order()
        with patch(COBRAR, return_value=aprovado()):
            result = CheckoutService.create_payment(order, 'voucher', DADOS)

        self.assertTrue(result['success'], result)
        sp = StorePayment.objects.get(order=order)
        self.assertEqual(sp.status, StorePayment.PaymentStatus.COMPLETED)
        self.assertEqual(sp.payment_method, StorePayment.PaymentMethod.VOUCHER)
        self.assertEqual(sp.external_id, 'or_9')
        self.assertEqual(sp.store_id, self.store.id)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_a_cobranca_e_sempre_o_total_cheio(self):
        """Tudo ou nada: nunca um valor parcial."""
        order = self._order('25.00')
        with patch(COBRAR, return_value=aprovado()):
            CheckoutService.create_payment(order, 'voucher', DADOS)
        self.assertEqual(StorePayment.objects.get(order=order).amount, Decimal('25.00'))

    def test_recusado_nao_marca_pedido_como_pago(self):
        order = self._order()
        with patch(COBRAR, return_value=recusado()):
            result = CheckoutService.create_payment(order, 'voucher', DADOS)

        self.assertFalse(result['success'])
        self.assertIn('saldo', result['error'].lower())
        self.assertEqual(
            StorePayment.objects.get(order=order).status,
            StorePayment.PaymentStatus.FAILED,
        )
        order.refresh_from_db()
        self.assertNotEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_pendente_nao_vira_falha_e_espera_o_webhook(self):
        """`pending` marcado como FAILED faria o webhook chegar depois
        confirmando um pagamento que o sistema ja deu como perdido — o mesmo
        desencontro que custou dinheiro em 31/ago. A linha fica PENDING."""
        order = self._order()
        with patch(COBRAR, return_value=pendente()):
            result = CheckoutService.create_payment(order, 'voucher', DADOS)

        self.assertTrue(result['success'], result)
        self.assertTrue(result.get('pending'))
        sp = StorePayment.objects.get(order=order)
        self.assertEqual(sp.status, StorePayment.PaymentStatus.PENDING)
        order.refresh_from_db()
        self.assertNotEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertNotEqual(order.payment_status, StoreOrder.PaymentStatus.FAILED)

    def test_pendente_nao_move_o_payment_status_do_pedido(self):
        """Nao basta 'nao e PAID nem FAILED': o valor tem que ser o MESMO de
        antes. `_sync_with_order` grava incondicionalmente, e hoje isso e um
        no-op so porque o Django cacheia o objeto do pedido na FK. Se essa
        gravacao um dia mudar de valor, e ESTE teste que avisa."""
        order = self._order()
        antes = order.payment_status

        with patch(COBRAR, return_value=pendente()):
            CheckoutService.create_payment(order, 'voucher', DADOS)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, antes)

    def test_valor_parcial_e_recusado_no_vale(self):
        order = self._order('25.00')
        with patch(COBRAR) as cobrar:
            r = CheckoutService.create_payment(
                order, 'voucher', DADOS, amount=Decimal('10.00'),
            )
        self.assertFalse(r['success'])
        self.assertEqual(cobrar.call_count, 0)
        self.assertFalse(StorePayment.objects.filter(order=order).exists())

    def test_pendente_nao_fala_em_recusa_para_o_cliente(self):
        """Nada de "use outro cartao ou pague no PIX" sobre cobranca em voo."""
        order = self._order()
        with patch(COBRAR, return_value=pendente()):
            result = CheckoutService.create_payment(order, 'voucher', DADOS)
        texto = (result.get('message') or '') + (result.get('error') or '')
        self.assertNotIn('PIX', texto)
        self.assertNotIn('autorizado', texto.lower())

    def test_loja_sem_gateway_recusa_com_mensagem_clara(self):
        outra = Store.objects.create(
            name='Sem Vale', slug='sem-vale', owner=self.owner, status='active',
        )
        order = self._order(store=outra)
        result = CheckoutService.create_payment(order, 'voucher', DADOS)
        self.assertFalse(result['success'])
        self.assertIn('vale', result['error'].lower())

    def test_cpf_ausente_e_recusado_antes_da_rede(self):
        """holder_document e obrigatorio no voucher. Sem ele o Pagar.me recusa —
        melhor recusar aqui, com texto que diz o que fazer."""
        order = self._order()
        with patch(COBRAR) as cobrar:
            result = CheckoutService.create_payment(
                order, 'voucher', {**DADOS, 'holder_document': ''},
            )
        self.assertFalse(result['success'])
        self.assertIn('cpf', result['error'].lower())
        self.assertEqual(cobrar.call_count, 0)

    def test_o_token_nunca_vai_para_o_banco(self):
        order = self._order()
        with patch(COBRAR, return_value=aprovado()):
            CheckoutService.create_payment(order, 'voucher', DADOS)
        sp = StorePayment.objects.get(order=order)
        self.assertNotIn('tok_1', str(sp.gateway_response))
        self.assertNotIn('tok_1', str(sp.metadata))
