"""O poller alcança a cobrança que guarda um id de PREFERENCE, não de pagamento.

A rede de segurança do webhook é `reconcile_pending_pix_payments`: quando o
aviso do Mercado Pago se perde (502 num restart, queda de rede), o poller
consulta o MP e dispara o mesmo fluxo.

Só que ele consulta com `payment().get(external_id)` — e as cobranças de LINK e
de redirect de cartão guardam em `external_id` o id da **preference**
(`235180147-23105bd9-…`), porque o id do pagamento só nasce quando o cliente
paga. `GET /v1/payments/235180147-…` responde 404, o poller desiste, e a
cobrança fica pendente para sempre.

Foi o buraco que deixou os R$ 35,99 da Dênia irrecuperáveis pelas duas vias ao
mesmo tempo: o webhook não achou a loja, e o poller não achou o pagamento.

Contrato: id que não é numérico é preference — procura-se pelo
`external_reference`, que é único por cobrança.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tasks import reconcile_pending_pix_payments

CREDENCIAL = {'provider': 'mercadopago', 'access_token': 'TOKEN', 'sandbox': False}


class PollerAchaPagamentoDeLinkTests(TestCase):
    def setUp(self):
        User = get_user_model()
        dono = User.objects.create_user(username='d_poll', email='d@poll.com', password='x')
        self.store = Store.objects.create(name='L', slug='loja-poll', owner=dono)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='DENIA OLIVEIRA',
            customer_email='d@t.com', customer_phone='556384122444',
            subtotal=Decimal('35.99'), total=Decimal('35.99'),
            payment_method='credit_card',
        )
        self.cobranca = StorePayment.objects.create(
            order=self.order, store=self.store, amount=Decimal('35.99'),
            payment_method=StorePayment.PaymentMethod.CREDIT_CARD,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='235180147-23105bd9-221c-4342-bef8-e60a13b83e97',
            external_reference=str(self.order.id),
        )

    def _rodar(self, sdk):
        with mock.patch('mercadopago.SDK', return_value=sdk), \
             mock.patch.object(
                 CheckoutService, 'get_payment_credentials', return_value=CREDENCIAL,
             ), \
             mock.patch('apps.stores.services.realtime_service.broadcast_order_event'), \
             mock.patch('apps.stores.api.webhooks.MercadoPagoWebhookView'):
            reconcile_pending_pix_payments()

    def _sdk(self, resultado_da_busca):
        sdk = mock.MagicMock()
        # GET com id de preference: é o que o MP responde de verdade.
        sdk.payment.return_value.get.return_value = {'status': 404, 'response': {}}
        sdk.payment.return_value.search.return_value = {
            'status': 200, 'response': {'results': resultado_da_busca},
        }
        return sdk

    def test_procura_pelo_external_reference_quando_o_id_e_de_preference(self):
        sdk = self._sdk([{
            'id': 176516131214, 'status': 'approved',
            'external_reference': str(self.order.id),
            'payment_type_id': 'credit_card', 'payment_method_id': 'master',
            'transaction_amount': 35.99,
        }])

        self._rodar(sdk)

        sdk.payment.return_value.search.assert_called()
        self.order.refresh_from_db()
        self.cobranca.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(self.cobranca.status, StorePayment.PaymentStatus.COMPLETED)

    def test_troca_o_id_da_preference_pelo_id_do_pagamento(self):
        # Sem isto o próximo ciclo repete a busca e o webhook do MP continua
        # sem casar por external_id.
        sdk = self._sdk([{
            'id': 176516131214, 'status': 'approved',
            'external_reference': str(self.order.id),
            'payment_type_id': 'credit_card',
        }])

        self._rodar(sdk)

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.external_id, '176516131214')

    def test_busca_sem_resultado_nao_altera_nada(self):
        self._rodar(self._sdk([]))

        self.order.refresh_from_db()
        self.cobranca.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PENDING)
        self.assertEqual(self.cobranca.status, StorePayment.PaymentStatus.PENDING)

    def test_pagamento_recusado_na_busca_nao_marca_pago(self):
        self._rodar(self._sdk([{
            'id': 176516131214, 'status': 'rejected',
            'external_reference': str(self.order.id),
        }]))

        self.order.refresh_from_db()
        self.assertNotEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_id_numerico_continua_indo_pelo_get_direto(self):
        # PIX guarda o id numérico; não pode passar a fazer busca à toa.
        self.cobranca.external_id = '174591801898'
        self.cobranca.save(update_fields=['external_id'])
        sdk = mock.MagicMock()
        sdk.payment.return_value.get.return_value = {
            'status': 200,
            'response': {
                'id': 174591801898, 'status': 'approved',
                'external_reference': str(self.order.id), 'payment_type_id': 'bank_transfer',
            },
        }

        self._rodar(sdk)

        sdk.payment.return_value.search.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PAID)
