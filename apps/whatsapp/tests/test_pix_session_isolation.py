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
        with patch(
            'apps.whatsapp.tasks.checkout_tasks.finalize_whatsapp_order_task.delay'
        ) as delay:
            result = h.handle({'reply_id': 'pay_pix', 'reply_title': '', 'original_message': ''})
        delay.assert_called_once()
        self.assertNotIn('PIXVELHO', result.response_text or '')
        self.assertIn('recebido', (result.response_text or '').lower())

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


class AsyncCheckoutTaskTest(_Base):
    """finalize_whatsapp_order_task: finaliza, envia e libera o lock."""

    def _seed_cart(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})

    def test_task_finalizes_and_sends_buttons(self):
        from django.core.cache import cache
        from apps.whatsapp.tasks.checkout_tasks import finalize_whatsapp_order_task
        self._seed_cart()
        cache.set('lock-teste', '1', timeout=60)
        fake = HandlerResult.buttons(body='PIXNOVO123', buttons=[{'id': 'pix_copy', 'title': 'COPIAR CODIGO PIX'}])
        with patch.object(InteractiveReplyHandler, '_finalize_order', return_value=fake) as fin, \
             patch('apps.whatsapp.services.message_service.MessageService.send_interactive_buttons') as send_btn:
            finalize_whatsapp_order_task.apply(kwargs=dict(
                account_id=str(self.account.id),
                conversation_id=str(self.conversation.id),
                profile_id=str(self.profile.id),
                payment_method='pix',
                lock_key='lock-teste',
            ))
        fin.assert_called_once()
        send_btn.assert_called_once()
        self.assertEqual(send_btn.call_args.kwargs['body_text'], 'PIXNOVO123')
        self.assertIsNone(cache.get('lock-teste'), 'lock não liberado')
        h = self._handler()
        self.assertEqual(h._get_session_manager().get_pending_order_items(), [],
                         'itens pendentes não limpos após finalizar')

    def test_task_sends_text_result(self):
        from apps.whatsapp.tasks.checkout_tasks import finalize_whatsapp_order_task
        self._seed_cart()
        fake = HandlerResult.text('🧾 Pedido #X recebido! Link: https://mp.com/x')
        with patch.object(InteractiveReplyHandler, '_finalize_order', return_value=fake), \
             patch('apps.whatsapp.services.message_service.MessageService.send_text_message') as send_txt:
            finalize_whatsapp_order_task.apply(kwargs=dict(
                account_id=str(self.account.id),
                conversation_id=str(self.conversation.id),
                profile_id=str(self.profile.id),
                payment_method='card',
            ))
        send_txt.assert_called_once()
        self.assertIn('recebido', send_txt.call_args.kwargs['text'])


class FlowPolishTest(_Base):
    def test_add_more_items_shows_menu_not_error(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': 'add_more_items', 'reply_title': '', 'original_message': ''})
        blob = (result.response_text or '') + str(result.interactive_data or {})
        self.assertNotIn('Erro ao processar', blob)

    def test_sauce_upsell_confirms_addition(self):
        sauce = StoreProduct.objects.create(
            store=self.store, name='Molho Pesto', slug='molho-pesto-pix', price=12, is_active=True,
        )
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': f'sauce_{sauce.id}', 'reply_title': '', 'original_message': ''})
        blob = (result.response_text or '') + str(result.interactive_data or {})
        self.assertIn('Molho Pesto', blob)
        self.assertIn('adicionado', blob)


class DynamicUpsellTest(_Base):
    """Upsell 100% dinâmico: categorias-complemento do cardápio DA LOJA."""

    def _category(self, name):
        from apps.stores.models import StoreCategory
        return StoreCategory.objects.create(
            store=self.store, name=name, slug=name.lower().replace(' ', '-'), is_active=True,
        )

    def test_checkout_without_upsell_categories_goes_straight_to_delivery(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': 'checkout_now', 'reply_title': '', 'original_message': ''})
        ids = {b['id'] for b in (result.interactive_data or {}).get('buttons', [])}
        self.assertIn('order_delivery', ids, 'Sem categoria-complemento deveria ir direto pra entrega')

    def test_checkout_offers_store_own_categories(self):
        cat = self._category('Sobremesas')
        pudim = StoreProduct.objects.create(
            store=self.store, name='Pudim', slug='pudim-up', price=15, is_active=True, category=cat,
        )
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': 'checkout_now', 'reply_title': '', 'original_message': ''})
        data = result.interactive_data or {}
        ids = {b['id'] for b in data.get('buttons', [])}
        self.assertIn(f'upsell_{pudim.id}', ids)
        self.assertIn('Sobremesa', data.get('body', ''))
        self.assertIn('skip_upsell', ids)

    def test_upsell_click_adds_confirms_and_advances(self):
        cat = self._category('Sobremesas')
        pudim = StoreProduct.objects.create(
            store=self.store, name='Pudim', slug='pudim-up2', price=15, is_active=True, category=cat,
        )
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        h.handle({'reply_id': 'checkout_now', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': f'upsell_{pudim.id}', 'reply_title': '', 'original_message': ''})
        blob = (result.response_text or '') + str(result.interactive_data or {})
        self.assertIn('Pudim', blob)
        self.assertIn('adicionado', blob)
        ids = {i['product_id'] for i in self._pending()}
        self.assertIn(str(pudim.id), ids)
        # Sem mais etapas → pergunta de entrega na mesma mensagem
        btn_ids = {b['id'] for b in (result.interactive_data or {}).get('buttons', [])}
        self.assertIn('order_delivery', btn_ids)

    def test_category_already_in_cart_is_skipped(self):
        cat = self._category('Bebidas')
        coca = StoreProduct.objects.create(
            store=self.store, name='Coca', slug='coca-up', price=8, is_active=True, category=cat,
        )
        h = self._handler()
        h.handle({'reply_id': f'product_{self.product.id}', 'reply_title': '', 'original_message': ''})
        h.handle({'reply_id': f'product_{coca.id}', 'reply_title': '', 'original_message': ''})
        result = h.handle({'reply_id': 'checkout_now', 'reply_title': '', 'original_message': ''})
        ids = {b['id'] for b in (result.interactive_data or {}).get('buttons', [])}
        self.assertIn('order_delivery', ids, 'Já tem bebida no carrinho — não deveria ofertar de novo')

    def _pending(self):
        h = self._handler()
        return h._get_session_manager().get_pending_order_items() or []


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
