"""Cristiane recebeu "Pagamento Confirmado!" de hora em hora (11/nov/2026).

CE-2611118547: a cliente abriu o link de cartão (cobrança 1, external_id =
preference) e acabou pagando no PIX (cobrança 2, external_id = 187955429089,
`completed`). Às 14:39 o poller achou o pagamento pelo external_reference e
trocou o id da cobrança 1 para 187955429089 — o MESMO da cobrança 2.

Daí em diante a cobrança 1 ficou `pending` para sempre: o
`process_payment_webhook` casa pela mais recente com aquele id (a 2, já
concluída). A chave de idempotência vence em 1h, e a cada hora o poller
"reconciliava" de novo e mandava outra confirmação — 15:39, 16:39, 17:39,
18:39, mesmo com o pedido já entregue.

Contrato:
  - cobrança pendente cujo pagamento já foi registrado em OUTRA cobrança é
    duplicata: vira `cancelled` e sai do poller;
  - confirmação no WhatsApp só sai quando ESTA rodada fez o pedido virar pago.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tasks import reconcile_pending_pix_payments

CREDENCIAL = {'provider': 'mercadopago', 'access_token': 'TOKEN', 'sandbox': False}
ID_DO_PIX = '187955429089'


class PollerNaoRepeteConfirmacaoTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        dono = User.objects.create_user(username='d_cris', email='d@cris.com', password='x')
        self.store = Store.objects.create(name='L', slug='loja-cris', owner=dono)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cristiane',
            customer_email='c@t.com', customer_phone='5563984704494',
            subtotal=Decimal('38.99'), total=Decimal('38.99'),
            payment_method='pix',
        )
        self.cartao = StorePayment.objects.create(
            order=self.order, store=self.store, amount=Decimal('38.99'),
            payment_method=StorePayment.PaymentMethod.CREDIT_CARD,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='235180147-aaaa-bbbb', external_reference=str(self.order.id),
        )
        self.pix = StorePayment.objects.create(
            order=self.order, store=self.store, amount=Decimal('38.99'),
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_id=ID_DO_PIX,
        )
        # O PIX foi pago e o webhook processou na hora.
        CheckoutService.process_payment_webhook(ID_DO_PIX, 'approved')
        self.order.refresh_from_db()
        self.pix.refresh_from_db()
        assert self.order.payment_status == StoreOrder.PaymentStatus.PAID
        assert self.pix.status == StorePayment.PaymentStatus.COMPLETED

    def _sdk(self):
        sdk = mock.MagicMock()
        aprovado = {
            'id': int(ID_DO_PIX), 'status': 'approved',
            'external_reference': str(self.order.id), 'payment_type_id': 'bank_transfer',
        }
        sdk.payment.return_value.get.return_value = {'status': 200, 'response': aprovado}
        sdk.payment.return_value.search.return_value = {
            'status': 200, 'response': {'results': [aprovado]},
        }
        return sdk

    def _rodar(self):
        with mock.patch('mercadopago.SDK', return_value=self._sdk()), \
             mock.patch.object(CheckoutService, 'get_payment_credentials', return_value=CREDENCIAL), \
             mock.patch('apps.stores.services.realtime_service.broadcast_order_event'), \
             mock.patch('apps.stores.api.webhooks.MercadoPagoWebhookView') as view:
            reconcile_pending_pix_payments()
        return view.return_value._send_payment_confirmation_whatsapp

    def test_varias_horas_seguidas_nenhuma_confirmacao_repetida(self):
        for _ in range(4):  # 15:39, 16:39, 17:39, 18:39
            enviar = self._rodar()
            enviar.assert_not_called()
            cache.clear()  # a chave de idempotência venceu

    def test_cobranca_duplicada_e_cancelada(self):
        self._rodar()
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.status, StorePayment.PaymentStatus.CANCELLED)
        self.pix.refresh_from_db()
        self.assertEqual(self.pix.status, StorePayment.PaymentStatus.COMPLETED)

    def test_cobranca_ja_presa_com_o_mesmo_id_tambem_e_cancelada(self):
        """Estado real de produção: a troca de id já aconteceu às 14:39."""
        StorePayment.objects.filter(pk=self.cartao.pk).update(external_id=ID_DO_PIX)
        enviar = self._rodar()
        enviar.assert_not_called()
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.status, StorePayment.PaymentStatus.CANCELLED)


class ConfirmacaoUmaVezPorPedidoTests(TestCase):
    """Trava no próprio envio: vale para o webhook do MP (que reenvia após 1h) e o poller."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        dono = User.objects.create_user(username='d_conf', email='d@conf.com', password='x')
        self.store = Store.objects.create(name='L', slug='loja-conf', owner=dono)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cristiane',
            customer_email='c@t.com', customer_phone='5563984704494',
            subtotal=Decimal('38.99'), total=Decimal('38.99'),
        )

    def _enviar(self, ja_enviada=False):
        from apps.stores.api.webhooks import MercadoPagoWebhookView
        with mock.patch.object(Store, 'get_whatsapp_account', return_value=mock.MagicMock()), \
             mock.patch('apps.automation.mensageiro.enviar_texto', return_value=mock.MagicMock()) as enviar, \
             mock.patch('apps.stores.api.webhooks._confirmacao_ja_enviada', return_value=ja_enviada):
            MercadoPagoWebhookView()._send_payment_confirmation_whatsapp(self.order)
        return enviar

    def test_primeira_confirmacao_sai(self):
        self.assertEqual(self._enviar().call_count, 1)

    def test_confirmacao_ja_registrada_na_conversa_nao_sai_de_novo(self):
        self.assertEqual(self._enviar(ja_enviada=True).call_count, 0)

    def test_duas_chamadas_seguidas_so_uma_sai(self):
        """Webhook e poller no mesmo minuto: a trava de cache segura a segunda."""
        self.assertEqual(self._enviar().call_count, 1)
        self.assertEqual(self._enviar().call_count, 0)
