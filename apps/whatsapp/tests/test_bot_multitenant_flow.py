"""Sanitização multi-tenant do bot de pedidos (14/jul).

1. Multi-produto: selecionar um produto NÃO pode descartar os anteriores —
   itens pendentes acumulam (mesmo produto soma quantidade).
2. Quantidade: cliente ajusta a quantidade via botões (qty_/setqty_).
3. Toggle `bot_order_enabled` (settings do CompanyProfile): lojista decide se
   o bot fecha pedidos pelo WhatsApp. OFF → intents/cliques de pedido recebem
   redirecionamento pro site; cardápio/horário/atendente continuam.
4. Textos genéricos: nada de "salada" hardcoded pra loja que não é a Cê Saladas.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.catalog import MenuRequestHandler
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono3', email='dono3@loja.com', password='x'
        )
        self.store = Store.objects.create(
            name='Cantina Massas', slug='cantina-massas', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='Cantina', phone_number_id='PHCANT', waba_id='WCANT',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        # perfil criado pelo signal da CONTA fica órfão; remove pra evitar duplicidade
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563988880000',
        )
        self.p1 = StoreProduct.objects.create(
            store=self.store, name='Lasanha Bolonhesa', slug='lasanha-bolonhesa', price=45, is_active=True,
        )
        self.p2 = StoreProduct.objects.create(
            store=self.store, name='Rondelli de Frango', slug='rondelli-frango', price=39, is_active=True,
        )

    def _handler(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)

    def _pending_items(self):
        h = self._handler()
        return h._get_session_manager().get_pending_order_items() or []


class MultiProductCartTest(_Base):
    def test_selecting_second_product_keeps_first(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.p1.id}', 'reply_title': '', 'original_message': ''})
        h.handle({'reply_id': f'product_{self.p2.id}', 'reply_title': '', 'original_message': ''})
        items = self._pending_items()
        ids = {i['product_id'] for i in items}
        self.assertEqual(ids, {str(self.p1.id), str(self.p2.id)},
                         'Selecionar o 2º produto descartou o 1º')

    def test_selecting_same_product_twice_sums_quantity(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.p1.id}', 'reply_title': '', 'original_message': ''})
        h.handle({'reply_id': f'product_{self.p1.id}', 'reply_title': '', 'original_message': ''})
        items = self._pending_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['quantity'], 2)

    def test_setqty_updates_quantity(self):
        h = self._handler()
        h.handle({'reply_id': f'product_{self.p1.id}', 'reply_title': '', 'original_message': ''})
        h.handle({'reply_id': f'setqty_{self.p1.id}_4', 'reply_title': '', 'original_message': ''})
        items = self._pending_items()
        self.assertEqual(items[0]['quantity'], 4)

    def test_add_offers_more_items_and_checkout(self):
        h = self._handler()
        result = h.handle({'reply_id': f'product_{self.p1.id}', 'reply_title': '', 'original_message': ''})
        button_ids = {b['id'] for b in (result.interactive_data or {}).get('buttons', [])}
        self.assertIn('add_more_items', button_ids)
        self.assertIn('checkout_now', button_ids)


class BotOrderToggleTest(_Base):
    def setUp(self):
        super().setUp()
        s = dict(self.profile.settings or {})
        s['bot_order_enabled'] = False
        self.profile.settings = s
        self.profile.save(update_fields=['settings'])
        self.account = WhatsAppAccount.objects.get(pk=self.account.pk)  # limpa cache de related

    def test_order_intent_redirects_to_site(self):
        from apps.automation.services.unified_service import ResponseSource, UnifiedService
        svc = UnifiedService(self.account, self.conversation, use_llm=False)
        resp = svc.process_message('quero fazer um pedido')
        self.assertIsNotNone(resp)
        self.assertNotEqual(resp.source, ResponseSource.SUPPRESSED)
        self.assertIn('site', resp.content.lower())

    def test_product_click_redirects_to_site(self):
        from apps.automation.services.unified_service import UnifiedService
        svc = UnifiedService(self.account, self.conversation, use_llm=False)
        resp = svc.process_message(
            '', interactive_reply={'type': 'list_reply', 'id': f'product_{self.p1.id}', 'title': ''},
        )
        self.assertIsNotNone(resp)
        self.assertIn('site', resp.content.lower())
        self.assertEqual(self._pending_items(), [])

    def test_menu_request_still_works(self):
        from apps.automation.services.unified_service import ResponseSource, UnifiedService
        svc = UnifiedService(self.account, self.conversation, use_llm=False)
        resp = svc.process_message('cardápio')
        self.assertIsNotNone(resp)
        self.assertNotEqual(resp.source, ResponseSource.SUPPRESSED)


class MultiTenantTextsTest(_Base):
    def test_menu_texts_have_no_salada_for_generic_store(self):
        result = MenuRequestHandler(self.account, self.conversation, self.profile).handle({})
        blob = ' '.join(filter(None, [
            result.response_text or '',
            str(result.interactive_data or {}),
        ])).lower()
        self.assertNotIn('salada', blob)

    def test_greeting_has_no_salada_button_for_generic_store(self):
        from apps.whatsapp.intents.handlers.greeting import GreetingHandler
        result = GreetingHandler(self.account, self.conversation, self.profile).handle({})
        blob = str(result.interactive_data or {}).lower() + (result.response_text or '').lower()
        self.assertNotIn('salada', blob)
