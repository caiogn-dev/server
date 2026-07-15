"""Melhorias de fluxo do bot (15/jul, rodada 8).

Gaps atacados (auditoria 15/jul):
- carrinho sem "ver/editar/remover/limpar" — só resumo reativo após adicionar;
- cancelar não cancelava o StoreOrder pendente (só a sessão);
- endereço re-coletado sempre, mesmo com endereço já validado na sessão;
- cart_items_count nunca atualizado no fluxo de botões → lembrete de carrinho
  abandonado (filtra cart_items_count>0) nunca disparava;
- checkout aceito com a loja fechada (is_open nunca checado);
- mensagem de erro de geocode com "Palmas - TO" hardcoded.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, CustomerSession
from apps.automation.services.session_manager import SessionManager
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.intents.handlers.order import CancelOrderHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

PHONE = '5563966660000'


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono8', email='dono8@loja.com', password='x'
        )
        self.store = Store.objects.create(
            name='Cantina Flow', slug='cantina-flow-v2', owner=self.owner,
            city='Paraíso do Tocantins',
        )
        self.account = WhatsAppAccount.objects.create(
            name='CantinaFlow', phone_number_id='PHFLOW', waba_id='WFLOW',
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
        self.lasanha = StoreProduct.objects.create(
            store=self.store, name='Lasanha', slug='lasanha-v2', price=45, is_active=True,
        )
        self.rondelli = StoreProduct.objects.create(
            store=self.store, name='Rondelli', slug='rondelli-v2', price=38, is_active=True,
        )

    def _handler(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)

    def _click(self, reply_id):
        return self._handler().handle(
            {'reply_id': reply_id, 'reply_title': '', 'original_message': ''}
        )

    def _add(self, product, qty=1):
        return self._click(f'add_{product.id}_{qty}')

    def _session(self):
        return SessionManager(self.account, PHONE).get_or_create_session()

    @staticmethod
    def _blob(result):
        return (result.response_text or '') + str(result.interactive_data or {})


class CartManagementTest(_Base):
    def test_cart_summary_offers_edit_cart(self):
        result = self._add(self.lasanha)
        self.assertIn('edit_cart', self._blob(result))

    def test_view_cart_shows_summary(self):
        self._add(self.lasanha, 2)
        result = self._click('view_cart')
        blob = self._blob(result)
        self.assertIn('Lasanha', blob)
        self.assertIn('90', blob)  # 2x45
        self.assertIn('checkout_now', blob)

    def test_view_cart_empty(self):
        result = self._click('view_cart')
        self.assertIn('vazio', self._blob(result).lower())

    def test_edit_cart_lists_remove_and_clear_rows(self):
        self._add(self.lasanha)
        self._add(self.rondelli)
        result = self._click('edit_cart')
        blob = self._blob(result)
        self.assertIn(f'remove_{self.lasanha.id}', blob)
        self.assertIn(f'remove_{self.rondelli.id}', blob)
        self.assertIn(f'qty_{self.lasanha.id}', blob)
        self.assertIn('clear_cart', blob)

    def test_remove_item_keeps_the_rest(self):
        self._add(self.lasanha)
        self._add(self.rondelli)
        result = self._click(f'remove_{self.lasanha.id}')
        blob = self._blob(result)
        self.assertIn('Rondelli', blob)
        items = SessionManager(self.account, PHONE).get_pending_order_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(str(items[0]['product_id']), str(self.rondelli.id))

    def test_remove_last_item_empties_cart(self):
        self._add(self.lasanha)
        result = self._click(f'remove_{self.lasanha.id}')
        self.assertIn('vazio', self._blob(result).lower())
        self.assertEqual(SessionManager(self.account, PHONE).get_pending_order_items(), [])

    def test_clear_cart_empties_everything(self):
        self._add(self.lasanha)
        self._add(self.rondelli)
        result = self._click('clear_cart')
        self.assertIn('esvazi', self._blob(result).lower())
        self.assertEqual(SessionManager(self.account, PHONE).get_pending_order_items(), [])
        self.assertEqual(self._session().cart_items_count, 0)


class CartCounterTest(_Base):
    def test_save_pending_items_updates_counter(self):
        self._add(self.lasanha, 2)
        self._add(self.rondelli, 1)
        self.assertEqual(self._session().cart_items_count, 3)

    def test_clear_pending_items_zeroes_counter(self):
        self._add(self.lasanha, 2)
        SessionManager(self.account, PHONE).clear_pending_order_items()
        self.assertEqual(self._session().cart_items_count, 0)


class CancelOrderTest(_Base):
    def _pending_order_session(self, payment_status='pending', status='pending'):
        order = StoreOrder.objects.create(
            store=self.store, customer_phone=PHONE,
            status=status, payment_status=payment_status,
            subtotal=45, total=45,
        )
        session = self._session()
        CustomerSession.objects.filter(pk=session.pk).update(
            status=CustomerSession.SessionStatus.PAYMENT_PENDING,
            pix_code='PIXCANCEL', order=order,
        )
        return order

    def test_cancel_cancels_unpaid_store_order(self):
        order = self._pending_order_session()
        h = CancelOrderHandler(self.account, self.conversation, self.profile)
        result = h.handle({'reply_id': 'cancel_order'})
        order.refresh_from_db()
        self.assertEqual(order.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertIn('cancelado', (result.response_text or '').lower())
        session = self._session()
        self.assertEqual(session.pix_code, '')

    def test_cancel_does_not_touch_paid_order(self):
        order = self._pending_order_session(payment_status='paid', status='confirmed')
        h = CancelOrderHandler(self.account, self.conversation, self.profile)
        h.handle({'reply_id': 'cancel_order'})
        order.refresh_from_db()
        self.assertEqual(order.status, StoreOrder.OrderStatus.CONFIRMED)


class SavedAddressTest(_Base):
    def _seed_address(self):
        mgr = SessionManager(self.account, PHONE)
        mgr.save_delivery_address_info(
            address='Rua das Árvores 100, Centro', fee=7.5,
            distance_km=2.4, duration_minutes=9, lat=-10.1, lng=-48.3,
        )

    def test_delivery_choice_offers_saved_address(self):
        self._add(self.lasanha)
        self._seed_address()
        result = self._click('order_delivery')
        blob = self._blob(result)
        self.assertIn('use_saved_address', blob)
        self.assertIn('new_address', blob)
        self.assertIn('Rua das Árvores', blob)

    def test_use_saved_address_goes_to_summary(self):
        self._add(self.lasanha)
        self._seed_address()
        self._click('order_delivery')
        result = self._click('use_saved_address')
        blob = self._blob(result)
        self.assertIn('Rua das Árvores', blob)
        self.assertIn('observa', blob.lower())  # pede observações
        self.assertIn('7,50', blob)  # taxa preservada

    def test_new_address_asks_for_address(self):
        self._add(self.lasanha)
        self._seed_address()
        self._click('order_delivery')
        result = self._click('new_address')
        self.assertIn('endereço', self._blob(result).lower())
        self.assertTrue(SessionManager(self.account, PHONE).is_waiting_for_address())

    def test_no_saved_address_asks_directly(self):
        self._add(self.lasanha)
        result = self._click('order_delivery')
        blob = self._blob(result)
        self.assertNotIn('use_saved_address', blob)
        self.assertIn('endereço', blob.lower())


class SchedulingTest(_Base):
    """Loja fechada NÃO bloqueia: aceita o pedido com agendamento."""

    HOURS = {
        d: {'open': '11:00', 'close': '14:00'}
        for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    }

    def _close_store(self):
        self.store.operating_hours = self.HOURS
        self.store.save(update_fields=['operating_hours'])
        # o handler enxerga o store cacheado no profile — sincroniza
        if getattr(self.profile, 'store', None) is not None:
            self.profile.store.refresh_from_db()
        return patch.object(Store, 'is_open', return_value=False)

    def test_checkout_when_closed_offers_scheduling_slots(self):
        self._add(self.lasanha)
        with self._close_store():
            result = self._click('checkout_now')
        blob = self._blob(result)
        self.assertIn('fechad', blob.lower())
        self.assertIn('sched_', blob)  # lista de horários das próximas aberturas

    def test_slot_click_saves_scheduling_and_continues(self):
        self._add(self.lasanha)
        with self._close_store():
            result = self._click('sched_2026-07-16_11:00')
        blob = self._blob(result)
        self.assertIn('gendad', blob)  # "Agendado"
        mgr = SessionManager(self.account, PHONE)
        sched = mgr.get_scheduling()
        self.assertEqual(sched['date'], '2026-07-16')
        self.assertEqual(sched['time'], '11:00')
        # fluxo continua: pergunta entrega/retirada (sem upsell nesta loja)
        self.assertIn('receber', blob.lower())

    def test_payment_when_closed_without_scheduling_offers_slots(self):
        self._add(self.lasanha)
        with self._close_store():
            result = self._click('pay_pix')
        self.assertIn('sched_', self._blob(result))

    def test_payment_when_closed_with_scheduling_proceeds(self):
        self._add(self.lasanha)
        with self._close_store():
            self._click('sched_2026-07-16_11:00')
            with patch(
                'apps.whatsapp.tasks.checkout_tasks.finalize_whatsapp_order_task.delay'
            ) as delay:
                result = self._click('pay_pix')
        delay.assert_called_once()
        self.assertIn('recebido', (result.response_text or '').lower())

    def test_checkout_open_store_has_no_scheduling_step(self):
        self._add(self.lasanha)
        result = self._click('checkout_now')
        self.assertNotIn('sched_', self._blob(result))

    def test_finalize_passes_scheduling_to_order_creation(self):
        self._add(self.lasanha)
        mgr = SessionManager(self.account, PHONE)
        mgr.save_scheduling('2026-07-16', '11:00')
        h = self._handler()
        with patch(
            'apps.whatsapp.services.create_order_from_whatsapp',
            return_value={'success': False, 'error': 'stop'},
        ) as create:
            h._finalize_order(
                [{'product_id': str(self.lasanha.id), 'quantity': 1}],
                delivery_method='pickup', payment_method='pix',
            )
        kwargs = create.call_args.kwargs
        self.assertEqual(str(kwargs.get('scheduled_date')), '2026-07-16')
        self.assertEqual(kwargs.get('scheduled_time'), '11:00')

    def test_clear_pending_items_clears_scheduling(self):
        mgr = SessionManager(self.account, PHONE)
        mgr.save_scheduling('2026-07-16', '11:00')
        mgr.clear_pending_order_items()
        self.assertIsNone(mgr.get_scheduling()['date'])


class FewerClicksTest(_Base):
    """Redução de cliques (15/jul): quanto menos passos, maior a conversão.

    - Observações viram opt-in: resumo já traz os botões de pagamento.
    - Checkout expresso: endereço salvo → carrinho vai DIRETO pro pagamento
      (1 clique), com '✏️ Alterar' para o fluxo completo.
    """

    def _seed_address(self):
        SessionManager(self.account, PHONE).save_delivery_address_info(
            address='Rua das Árvores 100, Centro', fee=7.5,
            distance_km=2.4, duration_minutes=9, lat=-10.1, lng=-48.3,
        )

    def test_pickup_summary_has_payment_buttons_inline(self):
        """Retirada: resumo + pagamento em UMA mensagem (sem pergunta de notas)."""
        self._add(self.lasanha)
        result = self._click('order_pickup')
        blob = self._blob(result)
        self.assertIn('pay_pix', blob)
        self.assertIn('pay_pickup', blob)
        self.assertIn('observa', blob.lower())  # dica opt-in continua visível

    def test_saved_address_summary_has_payment_buttons_inline(self):
        self._add(self.lasanha)
        self._seed_address()
        self._click('order_delivery')
        result = self._click('use_saved_address')
        blob = self._blob(result)
        self.assertIn('pay_pix', blob)
        self.assertIn('pay_card', blob)

    def test_typed_notes_still_captured_after_inline_buttons(self):
        self._add(self.lasanha)
        self._click('order_pickup')
        mgr = SessionManager(self.account, PHONE)
        self.assertTrue(mgr.is_waiting_for_notes())
        h = self._handler()
        result = h._handle_notes_input('sem cebola')
        fresh = SessionManager(self.account, PHONE)
        self.assertEqual(fresh.get_customer_notes(), 'sem cebola')
        self.assertIn('pay_pix', self._blob(result))

    def test_express_checkout_with_saved_address(self):
        """Recorrente: fechar pedido pula entrega/endereço → pagamento direto."""
        self._add(self.lasanha)
        self._seed_address()
        result = self._click('checkout_now')
        blob = self._blob(result)
        self.assertIn('pay_pix', blob)
        self.assertIn('change_details', blob)
        self.assertIn('Rua das Árvores', blob)
        # método de entrega já assumido
        mgr = SessionManager(self.account, PHONE)
        self.assertEqual(mgr.get_pending_delivery_method(), 'delivery')

    def test_express_pay_pix_enqueues_checkout(self):
        self._add(self.lasanha)
        self._seed_address()
        self._click('checkout_now')
        with patch(
            'apps.whatsapp.tasks.checkout_tasks.finalize_whatsapp_order_task.delay'
        ) as delay:
            result = self._click('pay_pix')
        delay.assert_called_once()
        self.assertIn('recebido', (result.response_text or '').lower())

    def test_change_details_falls_back_to_full_flow(self):
        self._add(self.lasanha)
        self._seed_address()
        self._click('checkout_now')
        result = self._click('change_details')
        self.assertIn('receber', self._blob(result).lower())

    def test_no_saved_address_keeps_delivery_question(self):
        self._add(self.lasanha)
        result = self._click('checkout_now')
        blob = self._blob(result)
        self.assertIn('order_delivery', blob)
        self.assertNotIn('change_details', blob)


class UpsellSingleStageTest(_Base):
    def test_heuristic_upsell_offers_only_one_stage(self):
        from apps.stores.models import StoreCategory
        bebidas = StoreCategory.objects.create(store=self.store, name='Bebidas', slug='bebidas-v2', is_active=True)
        sobremesas = StoreCategory.objects.create(store=self.store, name='Sobremesas', slug='sobremesas-v2', is_active=True)
        StoreProduct.objects.create(
            store=self.store, name='Coca', slug='coca-v2', price=6,
            is_active=True, category=bebidas,
        )
        StoreProduct.objects.create(
            store=self.store, name='Pudim', slug='pudim-v2', price=10,
            is_active=True, category=sobremesas,
        )
        self._add(self.lasanha)
        first = self._click('checkout_now')
        self.assertIn('upsell_', self._blob(first))
        second = self._click('skip_upsell')
        # heurística: só 1 etapa — a segunda categoria NÃO vira outra pergunta
        self.assertNotIn('upsell_', self._blob(second))

    def test_configured_categories_allow_two_stages(self):
        from apps.stores.models import StoreCategory
        bebidas = StoreCategory.objects.create(store=self.store, name='Bebidas', slug='bebidas-v2b', is_active=True)
        sobremesas = StoreCategory.objects.create(store=self.store, name='Sobremesas', slug='sobremesas-v2b', is_active=True)
        StoreProduct.objects.create(
            store=self.store, name='Coca', slug='coca-v2b', price=6,
            is_active=True, category=bebidas,
        )
        StoreProduct.objects.create(
            store=self.store, name='Pudim', slug='pudim-v2b', price=10,
            is_active=True, category=sobremesas,
        )
        self.profile.settings = {'bot_upsell_categories': ['bebidas', 'sobremesas']}
        self.profile.save(update_fields=['settings'])
        self._add(self.lasanha)
        self._click('checkout_now')
        second = self._click('skip_upsell')
        self.assertIn('upsell_', self._blob(second))


class GeoErrorMessageTest(_Base):
    def test_geocode_fail_message_uses_store_city(self):
        h = self._handler()
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=None):
            result = h._handle_address_input('Rua Inexistente 999')
        text = result.response_text or ''
        self.assertNotIn('Palmas - TO', text)
        self.assertIn('Paraíso do Tocantins', text)
