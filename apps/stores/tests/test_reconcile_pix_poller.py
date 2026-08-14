"""Reconciliação ativa de pagamentos PIX pendentes (30/jul).

Webhook do MP é o caminho rápido, mas se perde (ex.: 502 durante restart —
caso Georgia CE-2607301374, 30/jul). O poller consulta o MP para pagamentos
pendentes recentes e dispara o MESMO fluxo do webhook (process_payment_webhook),
com a MESMA chave de idempotência — webhook e poller nunca processam em dobro.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tasks import reconcile_pending_pix_payments

User = get_user_model()


def _mp_sdk_mock(status_value, external_reference=None):
    sdk = mock.MagicMock()
    sdk.payment.return_value.get.return_value = {
        'status': 200,
        'response': {'status': status_value, 'external_reference': external_reference},
    }
    return sdk


class ReconcilePixPollerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username='donopix', email='donopix@loja.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Loja PIX', slug='loja-pix', owner=self.owner,
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_phone='5563999990001',
            subtotal=50, total=50,
            payment_status='pending', payment_method='pix',
        )
        self.payment = StorePayment.objects.create(
            order=self.order, store=self.store,
            payment_id='pay-recon-1', external_id='999001',
            status='pending', payment_method='pix', amount=50,
        )
        self.creds = {'access_token': 'TEST-TOKEN'}

    def _run(self, sdk):
        with mock.patch('mercadopago.SDK', return_value=sdk), \
             mock.patch.object(CheckoutService, 'get_payment_credentials', return_value=self.creds), \
             mock.patch.object(CheckoutService, 'process_payment_webhook', return_value=self.order) as proc, \
             mock.patch('apps.stores.api.webhooks.MercadoPagoWebhookView') as view_cls, \
             mock.patch('apps.stores.services.realtime_service.broadcast_order_event'):
            reconcile_pending_pix_payments()
        return proc, view_cls

    def test_approved_on_mp_triggers_webhook_flow(self):
        proc, view_cls = self._run(_mp_sdk_mock('approved', external_reference=str(self.order.id)))
        proc.assert_called_once_with(
            '999001', 'approved', external_reference=str(self.order.id)
        )
        view_cls.return_value._send_payment_confirmation_whatsapp.assert_called_once()

    def test_still_pending_on_mp_does_nothing(self):
        proc, view_cls = self._run(_mp_sdk_mock('pending'))
        proc.assert_not_called()
        view_cls.return_value._send_payment_confirmation_whatsapp.assert_not_called()

    def test_cancelled_on_mp_processed_without_whatsapp(self):
        proc, view_cls = self._run(_mp_sdk_mock('cancelled'))
        proc.assert_called_once_with('999001', 'cancelled', external_reference=None)
        view_cls.return_value._send_payment_confirmation_whatsapp.assert_not_called()

    def test_old_payments_outside_window_are_skipped(self):
        """A janela é de 24h, não de 1h.

        Este teste usava 2 horas e ficou vermelho desde `b0e3dc8`, que alargou a
        janela de propósito: com 1 hora, o poller NUNCA alcançava um pagamento
        que o webhook tivesse perdido — quando a chave de idempotência expirava
        (TTL 3600s), o StorePayment já tinha saído da janela.

        24h é o horizonte certo porque é quanto dura o PIX do Mercado Pago
        (`expires_at = now + 24h`). Fora disso não há o que reconciliar.
        """
        StorePayment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(hours=30)
        )
        sdk = _mp_sdk_mock('approved')
        proc, _ = self._run(sdk)
        sdk.payment.return_value.get.assert_not_called()
        proc.assert_not_called()

    def test_idempotent_with_webhook(self):
        # Webhook já processou este (payment_id, status) — poller não repete.
        cache.add('mp_webhook:999001:approved', 1, timeout=3600)
        proc, _ = self._run(_mp_sdk_mock('approved'))
        proc.assert_not_called()

    def test_payment_without_external_id_is_skipped(self):
        StorePayment.objects.filter(pk=self.payment.pk).update(external_id='')
        sdk = _mp_sdk_mock('approved')
        proc, _ = self._run(sdk)
        sdk.payment.return_value.get.assert_not_called()

    def test_no_credentials_skips_gracefully(self):
        sdk = _mp_sdk_mock('approved')
        with mock.patch('mercadopago.SDK', return_value=sdk), \
             mock.patch.object(CheckoutService, 'get_payment_credentials', return_value=None), \
             mock.patch.object(CheckoutService, 'process_payment_webhook') as proc:
            reconcile_pending_pix_payments()
        proc.assert_not_called()
