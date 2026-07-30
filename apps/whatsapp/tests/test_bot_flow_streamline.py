"""Fluxo enxuto do bot (29/jul): sem passo intermediário, sem loop.

Decisão do produto: o bot NÃO pergunta "como prefere começar?" — pedido é
sempre pelo catálogo. Toda saída de menu se resume a *Cardápio* ou *Atendente*.

1. Clique em start_order/order_quick → catálogo direto (era o loop do
   "Pedido Rápido" que re-perguntava a mesma coisa).
2. Intent create_order sem itens na mensagem → catálogo direto.
3. Atalhos do UnknownHandler / AffirmativeHandler / fallback de reply
   desconhecido → apenas Cardápio + Atendente (sem "Fazer Pedido").
4. Saudação → Cardápio + Atendente (CTA custom da loja, ex. montar_salada,
   continua respeitado via settings['bot_cta']).
5. order_help (botão antigo ainda em conversas abertas) → atendente humano.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.fallback import AffirmativeHandler, UnknownHandler
from apps.whatsapp.intents.handlers.greeting import GreetingHandler
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.intents.handlers.order import CreateOrderHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono9', email='dono9@loja.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Cantina Fluxo', slug='cantina-fluxo', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CantinaF', phone_number_id='PHFLUX', waba_id='WFLUX',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563977770000',
        )
        self.p1 = StoreProduct.objects.create(
            store=self.store, name='Lasanha Quatro Queijos', slug='lasanha-4q', price=48, is_active=True,
        )

    def _interactive(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)

    @staticmethod
    def _button_ids(result):
        return [b['id'] for b in result.interactive_data.get('buttons', [])]


class StartOrderStraightToCatalogTest(_Base):
    def test_start_order_click_returns_catalog(self):
        result = self._interactive().handle(
            {'reply_id': 'start_order', 'reply_title': '🛒 Fazer Pedido', 'original_message': ''}
        )
        self.assertEqual(result.interactive_type, 'catalog_message',
                         'start_order deve abrir o catálogo direto, sem re-perguntar')

    def test_order_quick_click_returns_catalog(self):
        result = self._interactive().handle(
            {'reply_id': 'order_quick', 'reply_title': '⚡ Pedido Rápido', 'original_message': ''}
        )
        self.assertEqual(result.interactive_type, 'catalog_message',
                         'order_quick era loop ("Como prefere começar?") — deve abrir o catálogo')

    def test_order_help_click_hands_off_to_human(self):
        result = self._interactive().handle(
            {'reply_id': 'order_help', 'reply_title': '❓ Preciso de Ajuda', 'original_message': ''}
        )
        self.conversation.refresh_from_db()
        self.assertIn('atend', (result.response_text or '').lower())

    def test_create_order_intent_without_items_returns_catalog(self):
        handler = CreateOrderHandler(self.account, self.conversation, self.profile)
        result = handler.handle({'original_message': 'quero encomendar algumas coisas', 'entities': {}})
        self.assertEqual(result.interactive_type, 'catalog_message',
                         'create_order sem itens deve mostrar o catálogo, não botões de fluxo')


class MinimalShortcutsTest(_Base):
    def test_unknown_shortcuts_are_catalog_or_human_only(self):
        handler = UnknownHandler(self.account, self.conversation, self.profile)
        result = handler.handle({'original_message': 'xablau qualquer coisa', 'entities': {}})
        self.assertEqual(result.interactive_type, 'buttons')
        self.assertEqual(self._button_ids(result), ['view_menu', 'contact_support'])

    def test_affirmative_without_context_is_catalog_or_human_only(self):
        handler = AffirmativeHandler(self.account, self.conversation, self.profile)
        result = handler.handle({'original_message': 'sim', 'entities': {}})
        self.assertEqual(result.interactive_type, 'buttons')
        self.assertEqual(self._button_ids(result), ['view_menu', 'contact_support'])

    def test_unhandled_reply_fallback_is_catalog_or_human_only(self):
        result = self._interactive().handle(
            {'reply_id': 'id_inexistente_xyz', 'reply_title': 'Algo', 'original_message': ''}
        )
        self.assertEqual(result.interactive_type, 'buttons')
        self.assertEqual(self._button_ids(result), ['view_menu', 'contact_support'])


class GreetingButtonsTest(_Base):
    def test_greeting_has_no_default_start_order_button(self):
        handler = GreetingHandler(self.account, self.conversation, self.profile)
        result = handler.handle({'original_message': 'oi', 'entities': {}})
        ids = self._button_ids(result)
        self.assertNotIn('start_order', ids, 'Saudação não deve ter "Fazer Pedido" (duplica Cardápio)')
        self.assertIn('view_menu', ids)
        self.assertIn('contact_support', ids)

    def test_greeting_respects_custom_store_cta(self):
        self.profile.settings = {'bot_cta': {'id': 'montar_salada', 'title': '🥗 Montar Salada'}}
        self.profile.save(update_fields=['settings'])
        handler = GreetingHandler(self.account, self.conversation, self.profile)
        result = handler.handle({'original_message': 'oi', 'entities': {}})
        self.assertIn('montar_salada', self._button_ids(result))
