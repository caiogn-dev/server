"""Isolamento de pagamento entre pedidos na MESMA sessão (14/jul, rodada 5).

Bug real observado (conversa 556399547790): a sessão terminal reutilizada
carregava o pix_code do pedido anterior; ao montar um pedido NOVO, o
short-circuit de idempotência devolvia o QR/PIX antigo (valor errado) e o
pedido novo nunca era criado. Greeting também dizia "pedido sendo processado"
depois do pedido já entregue.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, CustomerSession
from apps.automation.services.session_manager import SessionManager
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.intents.handlers.base import HandlerResult
from apps.whatsapp.intents.handlers.greeting import GreetingHandler
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

PHONE = '5563977770000'


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono5', email='dono5@loja.com', password='x'
        )
        self.store = Store.objects.create(
            name='Cantina Massas', slug='cantina-massas-pix', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CantinaPix', phone_number_id='PHPIX', waba_id='WPIX',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number=PHONE,
        )
        self.product = StoreProduct.objects.create(
            store=self.store, name='Lasanha', slug='lasanha-pix', price=45, is_active=True,
        )

    def _terminal_session_with_stale_pix(self, order=None):
        return CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_stale',
            status=CustomerSession.SessionStatus.COMPLETED,
            pix_code='PIXVELHO26X90',
            pix_qr_code='qr-velho',
            payment_id='pay-velho',
            order=order,
        )

    def _handler(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)


class NewCartClearsStalePaymentTest(_Base):
    def test_save_pending_items_clears_stale_pix_from_terminal_session(self):
        stale = self._terminal_session_with_stale_pix()
        mgr = SessionManager(self.account, PHONE)
        mgr.save_pending_order_items([
            {'product_id': str(self.product.id), 'quantity': 1, 'price': 45.0},
        ])
        stale.refresh_from_db()
        self.assertEqual(stale.pix_code, '', 'pix_code do pedido antigo não foi limpo')
        self.assertEqual(stale.payment_id, '')
        self.assertIsNone(stale.order)
        self.assertEqual(stale.status, CustomerSession.SessionStatus.CART_CREATED)

    def test_product_click_on_terminal_session_clears_stale_pix(self):
        stale = self._terminal_session_with_stale_pix()
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        stale.refresh_from_db()
        self.assertEqual(stale.pix_code, '')


class PixIdempotencyScopeTest(_Base):
    def test_pay_pix_with_new_items_does_not_return_stale_pix(self):
        self._terminal_session_with_stale_pix()
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        with patch.object(
            InteractiveReplyHandler, '_finalize_order',
            return_value=HandlerResult.text('PEDIDO NOVO CRIADO'),
        ) as finalize:
            result = h.handle({'reply_id': 'pay_pix', 'reply_title': '', 'original_message': ''})
        finalize.assert_called_once()
        self.assertNotIn('PIXVELHO', result.response_text or '')

    def test_pay_pix_duplicate_click_without_items_reuses_pending_pix(self):
        # Sessão AGUARDANDO pagamento (pedido atual, itens já limpos) → reenviar é correto
        CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_pend',
            status=CustomerSession.SessionStatus.PAYMENT_PENDING,
            pix_code='PIXATUAL50X99',
        )
        h = self._handler()
        result = h.handle({'reply_id': 'pay_pix', 'reply_title': '', 'original_message': ''})
        blob = (result.response_text or '') + str(result.interactive_data or {})
        self.assertIn('PIXATUAL', blob)

    def test_pay_card_never_returns_session_pix(self):
        CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_card',
            status=CustomerSession.SessionStatus.PAYMENT_PENDING,
            pix_code='PIXATUAL50X99',
        )
        h = self._handler()
        result = h.handle({'reply_id': 'pay_card', 'reply_title': '', 'original_message': ''})
        blob = (result.response_text or '') + str(result.interactive_data or {})
        self.assertNotIn('PIXATUAL', blob)


class GreetingAfterDeliveredTest(_Base):
    def _greet(self):
        return GreetingHandler(self.account, self.conversation, self.profile).handle({})

    def test_greeting_after_delivered_order_is_fresh_welcome(self):
        order = StoreOrder.objects.create(
            store=self.store,
            customer_phone=PHONE,
            status=StoreOrder.OrderStatus.DELIVERED,
            subtotal=45,
            total=45,
        )
        CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_done',
            status=CustomerSession.SessionStatus.ORDER_PLACED,
            order=order,
        )
        result = self._greet()
        self.assertNotIn('sendo processado', (result.response_text or '').lower()
                         + str(result.interactive_data or {}).lower())

    def test_greeting_completed_session_without_order_is_fresh_welcome(self):
        CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_comp',
            status=CustomerSession.SessionStatus.COMPLETED,
        )
        result = self._greet()
        self.assertNotIn('sendo processado', (result.response_text or '').lower())

    def test_greeting_active_order_still_reports_processing(self):
        order = StoreOrder.objects.create(
            store=self.store,
            customer_phone=PHONE,
            status=StoreOrder.OrderStatus.PREPARING,
            subtotal=45,
            total=45,
        )
        CustomerSession.objects.create(
            company=self.profile,
            phone_number=PHONE,
            session_id=f'whatsapp_{PHONE}_prep',
            status=CustomerSession.SessionStatus.ORDER_PLACED,
            order=order,
        )
        result = self._greet()
        self.assertIn('sendo processado', (result.response_text or '').lower())
