"""Catálogo oficial + PIX copia-e-cola (20/jul).

1. "Ver cardápio" deve ENCAMINHAR pro catálogo oficial do WhatsApp
   (interactive type=catalog_message, carrinho nativo com múltiplos itens),
   não uma product_list com retailer_ids que não existem no catálogo.
2. Pedido vindo do catálogo oficial chega com retailer_id prefixado
   (ex.: "cs-<uuid>") — o webhook precisa resolver o produto mesmo assim,
   e nunca estourar com id não-UUID.
3. PIX: botão quick-reply "COPIAR CODIGO PIX" não copia nada (só ecoa o
   título). O código copia-e-cola deve ir SOZINHO numa mensagem de texto.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.base import IntentHandler
from apps.whatsapp.intents.handlers.catalog import MenuRequestHandler
from apps.whatsapp.intents.handlers.payment import PaymentStatusHandler
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services.webhook_service import resolve_catalog_products
from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono_cat', email='dono_cat@loja.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Cantina Catalogo', slug='cantina-catalogo', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CantinaCat', phone_number_id='PHCAT', waba_id='WCAT',
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
            store=self.store, name='Lasanha', slug='lasanha-cat', price=45, is_active=True,
        )


class MenuCatalogMessageTests(_Base):
    def test_menu_handler_returns_catalog_message(self):
        h = MenuRequestHandler(self.account, self.conversation, self.profile)
        res = h.handle({'original_message': 'cardápio'})
        self.assertTrue(res.use_interactive)
        self.assertEqual(res.interactive_type, 'catalog_message')
        # fallback pra loja sem catálogo conectado: lista interativa
        self.assertTrue(res.interactive_data.get('fallback_sections'))


class CatalogMessagePayloadTests(TestCase):
    def test_send_catalog_message_payload(self):
        account = WhatsAppAccount(
            name='X', phone_number_id='PH1', waba_id='W1',
            access_token='tok',
        )
        svc = WhatsAppAPIService(account)
        with patch.object(svc, '_make_request', return_value={'messages': [{'id': 'wamid.1'}]}) as mk:
            svc.send_catalog_message(
                to='5563900000000',
                body_text='Veja nosso catálogo 🛒',
                footer='Toque em Ver catálogo',
                thumbnail_product_retailer_id='cs-abc',
            )
        payload = mk.call_args.kwargs.get('data') or mk.call_args.args[2]
        self.assertEqual(payload['type'], 'interactive')
        self.assertEqual(payload['interactive']['type'], 'catalog_message')
        self.assertEqual(payload['interactive']['action']['name'], 'catalog_message')
        self.assertEqual(
            payload['interactive']['action']['parameters']['thumbnail_product_retailer_id'],
            'cs-abc',
        )


class RetailerIdResolutionTests(_Base):
    def test_prefixed_retailer_id_resolves_product(self):
        rid = f'cs-{self.p1.id}'
        products = resolve_catalog_products(self.store, [rid])
        self.assertIn(rid, products)
        self.assertEqual(products[rid].id, self.p1.id)

    def test_bare_uuid_still_resolves(self):
        rid = str(self.p1.id)
        products = resolve_catalog_products(self.store, [rid])
        self.assertEqual(products[rid].id, self.p1.id)

    def test_garbage_retailer_id_does_not_crash(self):
        products = resolve_catalog_products(self.store, ['itemapp-17', 'x'])
        self.assertEqual(products.get('itemapp-17'), None)


class PixPlainTextTests(_Base):
    def test_send_pix_confirmation_sends_code_as_plain_text(self):
        h = IntentHandler(self.account, self.conversation, self.profile)
        h._whatsapp_service = MagicMock()
        order = SimpleNamespace(
            id=uuid.uuid4(), order_number='1001', total=45.0,
            scheduled_date=None, scheduled_time='',
        )
        res = h._send_pix_confirmation(order, 'PIXCODE123COPIAECOLA')
        self.assertFalse(res.use_interactive)
        self.assertEqual(res.response_text, 'PIXCODE123COPIAECOLA')

    def test_payment_status_returns_code_as_plain_text(self):
        h = PaymentStatusHandler(self.account, self.conversation, self.profile)
        sm = h._get_session_manager()
        sm.set_payment_pending(pix_code='PIXCODE999', payment_id='pay1')
        res = h.handle({'original_message': 'pix'})
        self.assertFalse(res.use_interactive)
        self.assertEqual(res.response_text, 'PIXCODE999')


class AddressLoopEscapeTests(_Base):
    """Geo indisponível NUNCA pode prender o cliente num loop de endereço."""

    def _handler(self):
        h = IntentHandler(self.account, self.conversation, self.profile)
        h.store = self.store
        h._whatsapp_service = MagicMock()
        return h

    def test_second_geocode_failure_accepts_typed_address(self):
        h = self._handler()
        sm = h._get_session_manager()
        sm.set_waiting_for_address(True)
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=None):
            first = h._handle_address_input('604 Sul, alameda 14, casa 67')
            self.assertIn('Não consegui localizar', first.response_text or '')
            second = h._handle_address_input('604 Sul, alameda 14, casa 67')
        self.assertNotIn('Não consegui localizar', second.response_text or '')
        fresh = h._get_session_manager()  # manager cacheia a sessão em memória
        info = fresh.get_delivery_address_info()
        self.assertEqual(info.get('address'), '604 Sul, alameda 14, casa 67')
        self.assertFalse(fresh.is_waiting_for_address())

    def test_human_handoff_escapes_address_wait(self):
        from apps.automation.services.unified_service import LLMOrchestratorService
        h = self._handler()
        sm = h._get_session_manager()
        sm.set_waiting_for_address(True)
        svc = LLMOrchestratorService(
            account=self.account, conversation=self.conversation, use_llm=False,
        )
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=None):
            resp = svc.process_message('Tem como eu falar com um atendente')
        self.assertIn('atendente', (resp.content or '').lower())
        self.assertFalse(self._handler()._get_session_manager().is_waiting_for_address())


class UnknownFallbackTests(_Base):
    """Mensagem não identificada: atalhos úteis 1x, depois silêncio.

    Nada de "não consegui identificar" — pedido do usuário 20/jul.
    """

    def _unknown(self):
        from apps.whatsapp.intents.handlers.fallback import UnknownHandler
        h = UnknownHandler(self.account, self.conversation, self.profile)
        h.store = self.store
        return h

    def test_first_unknown_sends_shortcuts_without_apology(self):
        res = self._unknown().handle({'original_message': 'askjdh qweqwe'})
        self.assertTrue(res.use_interactive)
        body = (res.interactive_data or {}).get('body', '')
        self.assertNotIn('identificar', body.lower())
        self.assertNotIn('não entendi', body.lower())
        ids = [b['id'] for b in res.interactive_data['buttons']]
        self.assertIn('view_menu', ids)
        self.assertIn('contact_support', ids)

    def test_repeated_unknown_is_silent(self):
        self._unknown().handle({'original_message': 'askjdh qweqwe'})
        res2 = self._unknown().handle({'original_message': 'zxzxzx ababab'})
        self.assertTrue(res2.suppress)

    def test_unified_maps_suppress_to_suppressed(self):
        from apps.automation.services.unified_service import (
            LLMOrchestratorService, ResponseSource,
        )
        svc = LLMOrchestratorService(
            account=self.account, conversation=self.conversation, use_llm=False,
        )
        svc.process_message('askjdh qweqwe blorb')
        resp2 = svc.process_message('zxzxzx ababab blorb')
        self.assertEqual(resp2.source, ResponseSource.SUPPRESSED)

    def test_empty_message_is_suppressed(self):
        from apps.automation.services.unified_service import (
            LLMOrchestratorService, ResponseSource,
        )
        svc = LLMOrchestratorService(
            account=self.account, conversation=self.conversation, use_llm=False,
        )
        resp = svc.process_message('   ')
        self.assertEqual(resp.source, ResponseSource.SUPPRESSED)
