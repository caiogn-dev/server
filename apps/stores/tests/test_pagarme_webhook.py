from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment, StorePaymentGateway
from apps.webhooks.handlers.pagarme_handler import PagarmeHandler

User = get_user_model()

CONSULTA = 'apps.stores.services.pagarme_orders.consultar_order'


def corpo(tipo='order.paid', oid='or_9'):
    return {'id': 'hook_1', 'type': tipo, 'data': {'id': oid, 'status': 'paid'}}


def api(status_charge):
    return {'id': 'or_9', 'status': status_charge,
            'charges': [{'status': status_charge, 'last_transaction': {}}]}


class PagarmeWebhookTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-whk', password='x', email='owner-whk@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Whk', slug='loja-whk', owner=self.owner, status='active',
        )
        self.gateway = StorePaymentGateway.objects.create(
            store=self.store, name='Pagar.me', gateway_type='pagarme',
            api_key='sk_test_x', public_key='pk_test_y', is_enabled=True,
            configuration={'voucher_brands': ['vr']},
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente',
            customer_phone='5599999999999', customer_email='cli@real.com',
            subtotal=Decimal('25.00'), total=Decimal('25.00'),
        )
        self.payment = StorePayment.objects.create(
            order=self.order, store=self.store, gateway=self.gateway,
            payment_method=StorePayment.PaymentMethod.VOUCHER,
            status=StorePayment.PaymentStatus.PENDING,
            amount=Decimal('25.00'), external_id='or_9',
        )

    def test_confirma_pelo_refetch_e_nao_pelo_corpo(self):
        """O corpo diz 'paid'. Se a API disser 'failed', vale a API.
        Confiar no corpo e como a receita fantasma nasceu."""
        with patch(CONSULTA, return_value=(200, api('failed'))) as consulta:
            PagarmeHandler().handle(None, corpo(), {})

        self.assertEqual(consulta.call_count, 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, StorePayment.PaymentStatus.FAILED)

    def test_pagamento_confirmado_marca_pedido(self):
        with patch(CONSULTA, return_value=(200, api('paid'))):
            PagarmeHandler().handle(None, corpo(), {})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, StorePayment.PaymentStatus.COMPLETED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_evento_repetido_nao_credita_duas_vezes(self):
        with patch(CONSULTA, return_value=(200, api('paid'))) as consulta:
            PagarmeHandler().handle(None, corpo(), {})
            PagarmeHandler().handle(None, corpo(), {})

        self.assertEqual(StorePayment.objects.filter(order=self.order).count(), 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, StorePayment.PaymentStatus.COMPLETED)
        # Reconsulta nas duas entregas (barato e correto), mas grava uma vez so.
        self.assertEqual(consulta.call_count, 2)

    def test_pagamento_ja_confirmado_nao_move_o_paid_at(self):
        """Regravar `paid_at` a cada reentrega moveria a hora do pagamento para
        a hora do ultimo webhook, e o relatorio de caixa passaria a mentir sobre
        quando o dinheiro entrou."""
        with patch(CONSULTA, return_value=(200, api('paid'))):
            PagarmeHandler().handle(None, corpo(), {})
        self.payment.refresh_from_db()
        primeiro = self.payment.paid_at

        with patch(CONSULTA, return_value=(200, api('paid'))):
            PagarmeHandler().handle(None, corpo(), {})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.paid_at, primeiro)

    def test_cobranca_desconhecida_nao_inventa_pagamento(self):
        """Backfill cego de cobranca orfa ja criou receita fantasma aqui.
        Sem StorePayment correspondente, o handler nao cria nada."""
        antes = StorePayment.objects.count()
        with patch(CONSULTA) as consulta:
            r = PagarmeHandler().handle(None, corpo(oid='or_desconhecida'), {})

        self.assertEqual(StorePayment.objects.count(), antes)
        self.assertEqual(consulta.call_count, 0)
        self.assertTrue(r.get('ignored'))

    def test_estorno_marca_refunded_sem_virar_falha_e_sem_mexer_no_paid_at(self):
        """CRITICAL 2: charge.refunded caindo em interpret()->failed fazia o
        handler gravar FAILED para um pagamento que teve sucesso e depois foi
        estornado. O caixa passaria a mentir sobre o que aconteceu."""
        with patch(CONSULTA, return_value=(200, api('paid'))):
            PagarmeHandler().handle(None, corpo(), {})
        self.payment.refresh_from_db()
        pago_em = self.payment.paid_at
        self.assertIsNotNone(pago_em)

        with patch(CONSULTA, return_value=(200, api('refunded'))):
            PagarmeHandler().handle(None, corpo(tipo='charge.refunded'), {})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, StorePayment.PaymentStatus.REFUNDED)
        self.assertNotEqual(self.payment.status, StorePayment.PaymentStatus.FAILED)
        self.assertEqual(self.payment.paid_at, pago_em)

    def test_pagarme_exige_assinatura_no_dispatcher(self):
        from apps.webhooks import dispatcher
        self.assertIn('pagarme', dispatcher._PROVIDERS_REQUIRE_SIGNATURE)
        self.assertIn('pagarme', dispatcher.WebhookDispatcherView._handlers)
