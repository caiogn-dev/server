"""
Testes e2e: fluxo conversacional completo via WhatsApp.

Cobertura:
1. Fluxo pickup → pagar na retirada → pedido criado
2. Fluxo delivery → endereço textual → PIX → pedido criado
3. Fluxo delivery → localização GPS → PIX → pedido criado
4. Guarda de sessão sem itens pendentes
5. Intent transacional (CREATE_ORDER) usa handler — NÃO chama LLM
6. Intent consultivo (GREETING) usa handler — pode chamar LLM
7. Pedido com stock rastreado decrementa estoque corretamente

Convenção:
  Cada fluxo é testado no nível dos handlers (IntentHandler / InteractiveReplyHandler),
  que é o nível em que as decisões de negócio são tomadas.
  Dependências externas (HERE Maps, MercadoPago, WhatsApp API) são sempre mockadas.

Executar:
    python manage.py test tests.test_conversation_flow_e2e --keepdb -v 2
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreProduct, StoreOrder
from apps.automation.models import CompanyProfile, CustomerSession
from apps.whatsapp.models import WhatsAppAccount
from apps.conversations.models import Conversation
from apps.whatsapp.intents.detector import IntentDetector, IntentType

User = get_user_model()

_PATCH_CREATE_ORDER = 'apps.whatsapp.intents.handlers.create_order_from_whatsapp'
_PATCH_WA_SEND = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message'
_PATCH_WA_INTERACTIVE = 'apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_interactive_message'
_PATCH_PAYMENT   = 'apps.whatsapp.services.order_service.CheckoutService.create_payment'
_PATCH_BROADCAST = 'apps.whatsapp.services.order_service.broadcast_order_event'


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='testpass',
    )


def _make_store(owner, slug='flow-e2e', lat='-10.18', lng='-48.33'):
    return Store.objects.create(
        owner=owner,
        name='Flow E2E Store',
        slug=slug,
        is_active=True,
        status='active',
        default_delivery_fee=Decimal('8.00'),
        latitude=lat,
        longitude=lng,
        delivery_enabled=True,
        pickup_enabled=True,
    )


def _make_product(store, name='Pizza', price=Decimal('25.00'),
                  track_stock=False, stock_quantity=0):
    return StoreProduct.objects.create(
        store=store,
        name=name,
        price=price,
        status=StoreProduct.ProductStatus.ACTIVE,
        track_stock=track_stock,
        stock_quantity=stock_quantity,
        is_active=True,
    )


def _make_account(owner, phone_number_id='123', phone_number='+5563900000099'):
    return WhatsAppAccount.objects.create(
        name='Test Account',
        phone_number_id=phone_number_id,
        waba_id='waba_test',
        phone_number=phone_number,
        access_token_encrypted='fake',
        status=WhatsAppAccount.AccountStatus.ACTIVE,
        owner=owner,
    )


def _make_conversation(account, phone='+5563900000050'):
    return Conversation.objects.create(
        account=account,
        phone_number=phone,
        contact_name='Cliente Teste',
        status=Conversation.ConversationStatus.OPEN,
    )


def _make_session(profile, phone):
    return CustomerSession.objects.create(
        company=profile,
        phone_number=phone,
        status=CustomerSession.SessionStatus.ACTIVE,
        cart_data={},
    )


def _make_handler(account, conversation, profile, handler_cls=None):
    """Instancia um handler com whatsapp_service mockado."""
    from apps.whatsapp.intents.handlers import InteractiveReplyHandler
    cls = handler_cls or InteractiveReplyHandler
    handler = cls(account, conversation, profile)
    handler._whatsapp_service = MagicMock()
    return handler


# ─── Base de setup compartilhado ─────────────────────────────────────────────

class ConversationFlowBase(TestCase):

    def setUp(self):
        self.owner = _make_user('flow_owner')
        self.store = _make_store(self.owner, 'flow-e2e-store')
        self.product = _make_product(self.store, 'Pizza Margherita', Decimal('25.00'))
        self.profile, _ = CompanyProfile.objects.get_or_create(
            store=self.store,
            defaults={'company_name': 'Flow Test Co'},
        )
        self.account = _make_account(self.owner, phone_number_id='e2e-001')
        # Link account → profile so IntentHandler._get_store() works
        self.account.company_profile = self.profile
        self.account.save()
        self.phone = '+5563900000050'
        self.conversation = _make_conversation(self.account, self.phone)
        self.session = _make_session(self.profile, self.phone)

    def _seed_session_items(self, qty=2):
        """Popula session com itens pendentes diretamente no cart_data."""
        self.session.cart_data = {
            'pending_items': [{'product_id': str(self.product.id), 'quantity': qty}],
        }
        self.session.save(update_fields=['cart_data'])

    def _seed_session_delivery(self, delivery_method='pickup', address='', fee=0.0,
                                lat=None, lng=None, components=None):
        data = dict(self.session.cart_data or {})
        data['pending_delivery_method'] = delivery_method
        data['delivery_address'] = address
        data['delivery_fee_calculated'] = fee
        if lat is not None:
            data['delivery_lat'] = lat
            data['delivery_lng'] = lng
        if components:
            data['delivery_address_components'] = components
        self.session.cart_data = data
        self.session.save(update_fields=['cart_data'])

    def _make_order(self):
        order = StoreOrder.objects.create(
            store=self.store,
            order_number='TEST-FLOW-001',
            customer_phone=self.phone,
            customer_name='Cliente Teste',
            status='received',
            subtotal=Decimal('50.00'),
            total=Decimal('50.00'),
            delivery_method='pickup',
            payment_method='cash',
        )
        return order

    def _handler(self, handler_cls=None):
        return _make_handler(self.account, self.conversation, self.profile, handler_cls)


# ─── Fluxo 1: Pickup + pagar na retirada ─────────────────────────────────────

class PickupCashFlowTest(ConversationFlowBase):
    """
    Simula:
      product selected → order_pickup clicked → pay_pickup clicked → pedido criado
    """

    def test_pickup_choice_goes_directly_to_payment_screen(self):
        """Escolher retirada deve pular coleta de endereço e ir para pagamento."""
        self._seed_session_items(qty=1)
        handler = self._handler()
        result = handler.handle({'reply_id': 'order_pickup'})
        # Deve perguntar pagamento (botão pay_pickup presente)
        self.assertIsNotNone(result)
        if result.use_interactive:
            button_ids = [b['id'] for b in result.interactive_data.get('buttons', [])]
            self.assertIn('pay_pickup', button_ids)

    def test_pay_pickup_creates_order_via_finalize(self):
        """pay_pickup com itens na sessão deve criar pedido com método cash."""
        self._seed_session_items(qty=2)
        self._seed_session_delivery('pickup')
        mock_order = self._make_order()

        handler = self._handler()
        with patch(_PATCH_CREATE_ORDER, return_value={
            'success': True,
            'order': mock_order,
            'order_number': mock_order.order_number,
            'payment_method': 'cash',
            'payment_data': {},
        }) as mock_create:
            result = handler.handle({'reply_id': 'pay_pickup'})

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        self.assertEqual(call_kwargs.kwargs.get('payment_method') or call_kwargs.args[4], 'cash')
        self.assertIsNotNone(result.response_text)
        self.assertIn('TEST-FLOW-001', result.response_text)

    def test_pay_pickup_without_items_returns_error(self):
        """Tentar finalizar pedido sem itens na sessão deve retornar mensagem de erro."""
        handler = self._handler()
        result = handler.handle({'reply_id': 'pay_pickup'})
        self.assertIsNotNone(result.response_text)
        self.assertIn('não encontrei', result.response_text.lower())


# ─── Fluxo 2: Delivery → endereço digitado → PIX ─────────────────────────────

class DeliveryTypedAddressFlowTest(ConversationFlowBase):
    """
    Simula:
      order_delivery clicked → endereço digitado → geocoded → taxa calculada
      → pay_pix clicked → pedido criado com delivery_address estruturado
    """

    def test_delivery_choice_requests_address(self):
        """Escolher entrega deve pedir endereço (não ir para pagamento)."""
        self._seed_session_items(qty=1)
        handler = self._handler()
        result = handler.handle({'reply_id': 'order_delivery'})
        self.assertIsNotNone(result.response_text)
        self.assertNotEqual(result.response_text, 'BUTTONS_SENT',
                            "delivery choice should ask for address, not payment buttons directly")
        self.assertIn('endereço', result.response_text.lower())

    def test_address_input_geocodes_and_saves_to_session(self):
        """Texto de endereço deve ser geocodificado e components salvos na sessão."""
        from apps.whatsapp.intents.handlers import UnknownHandler

        self._seed_session_items(qty=1)
        self.session.cart_data['waiting_for_address'] = True
        self.session.cart_data['pending_delivery_method'] = 'delivery'
        self.session.save(update_fields=['cart_data'])

        mock_geo = {
            'lat': -10.18, 'lng': -48.33,
            'formatted_address': 'Rua das Flores, 42, Palmas',
            'address': {
                'street': 'Rua das Flores',
                'houseNumber': '42',
                'city': 'Palmas',
                'stateCode': 'TO',
            },
        }
        mock_fee = {
            'fee': Decimal('9.00'), 'distance_km': 3.5, 'duration_minutes': 12,
            'is_within_area': True, 'zone': None, 'message': 'ok',
        }
        handler = _make_handler(self.account, self.conversation, self.profile, UnknownHandler)

        with patch(
            'apps.stores.services.here_maps_service.HereMapsService.geocode',
            return_value=mock_geo,
        ), patch(
            'apps.stores.services.here_maps_service.HereMapsService.calculate_delivery_fee',
            return_value=mock_fee,
        ):
            result = handler._handle_address_input('Rua das Flores, 42')

        # Deve pedir pagamento depois de confirmar endereço
        self.assertIsNotNone(result)
        self.session.refresh_from_db()
        components = self.session.cart_data.get('delivery_address_components', {})
        self.assertEqual(components.get('street'), 'Rua das Flores')
        self.assertEqual(components.get('city'), 'Palmas')

    def test_pay_pix_with_delivery_creates_order_with_fee(self):
        """pay_pix após delivery com fee na sessão cria pedido com taxa correta."""
        self._seed_session_items(qty=2)
        self._seed_session_delivery(
            delivery_method='delivery',
            address='Rua das Flores, 42',
            fee=9.0,
            lat=-10.18, lng=-48.33,
            components={'street': 'Rua das Flores', 'houseNumber': '42', 'city': 'Palmas'},
        )
        mock_order = self._make_order()
        mock_order.delivery_method = 'delivery'
        mock_order.total = Decimal('59.00')

        handler = self._handler()
        with patch(_PATCH_CREATE_ORDER, return_value={
            'success': True,
            'order': mock_order,
            'order_number': mock_order.order_number,
            'payment_method': 'pix',
            'payment_data': {'success': True, 'pix_code': '00020126...'},
        }) as mock_create:
            result = handler.handle({'reply_id': 'pay_pix'})

        mock_create.assert_called_once()
        kw = mock_create.call_args.kwargs
        self.assertEqual(kw.get('delivery_method'), 'delivery')
        self.assertEqual(kw.get('payment_method'), 'pix')
        self.assertAlmostEqual(kw.get('delivery_fee_override'), 9.0, places=1)
        self.assertIn('Rua das Flores', kw.get('delivery_address', ''))

    def test_invalid_address_returns_helpful_error(self):
        """Endereço não encontrado no geocode deve retornar mensagem de erro legível."""
        from apps.whatsapp.intents.handlers import UnknownHandler

        self._seed_session_items(qty=1)
        self.session.cart_data['waiting_for_address'] = True
        self.session.save(update_fields=['cart_data'])

        handler = _make_handler(self.account, self.conversation, self.profile, UnknownHandler)

        with patch(
            'apps.stores.services.here_maps_service.HereMapsService.geocode',
            return_value=None,
        ):
            result = handler._handle_address_input('endereço inválido !!!')

        self.assertIsNotNone(result.response_text)
        self.assertIn('não consegui', result.response_text.lower())


# ─── Fluxo 3: Delivery → localização GPS → PIX ───────────────────────────────

class DeliveryGPSFlowTest(ConversationFlowBase):
    """
    Simula:
      order_delivery clicked → localização GPS compartilhada → taxa calculada
      → pay_pix clicked → pedido criado com lat/lng no delivery_address
    """

    def test_location_input_saves_address_and_asks_payment(self):
        """GPS location deve calcular taxa e salvar na sessão sem geocode adicional."""
        from apps.whatsapp.intents.handlers import UnknownHandler

        self._seed_session_items(qty=1)
        self.session.cart_data['pending_delivery_method'] = 'delivery'
        self.session.save(update_fields=['cart_data'])

        mock_fee = {
            'fee': Decimal('8.00'), 'distance_km': 2.8, 'duration_minutes': 10,
            'is_within_area': True, 'zone': None, 'message': 'ok',
        }
        mock_rev = {
            'formatted_address': 'Alameda 1, Palmas',
            'street': 'Alameda 1',
            'city': 'Palmas',
            'state_code': 'TO',
        }

        handler = _make_handler(self.account, self.conversation, self.profile, UnknownHandler)

        with patch(
            'apps.stores.services.here_maps_service.HereMapsService.calculate_delivery_fee',
            return_value=mock_fee,
        ), patch(
            'apps.stores.services.here_maps_service.HereMapsService.reverse_geocode',
            return_value=mock_rev,
        ):
            result = handler._handle_location_input(-10.18, -48.33)

        # Deve pedir pagamento
        self.assertIsNotNone(result)
        self.session.refresh_from_db()
        self.assertAlmostEqual(
            self.session.cart_data.get('delivery_fee_calculated'), 8.0, places=2
        )
        self.assertAlmostEqual(self.session.cart_data.get('delivery_lat'), -10.18, places=4)

    def test_location_outside_area_returns_rejection_message(self):
        """Localização fora da área de entrega deve retornar mensagem de rejeição."""
        from apps.whatsapp.intents.handlers import UnknownHandler

        self._seed_session_items(qty=1)

        mock_fee = {
            'fee': Decimal('0'), 'distance_km': 50.0, 'duration_minutes': 90,
            'is_within_area': False, 'zone': None,
            'message': 'Fora da área de entrega',
        }

        handler = _make_handler(self.account, self.conversation, self.profile, UnknownHandler)

        with patch(
            'apps.stores.services.here_maps_service.HereMapsService.calculate_delivery_fee',
            return_value=mock_fee,
        ), patch(
            'apps.stores.services.here_maps_service.HereMapsService.reverse_geocode',
            return_value={'formatted_address': 'Longe, Outro Estado'},
        ):
            result = handler._handle_location_input(-20.0, -50.0)

        self.assertIsNotNone(result.response_text)
        self.assertIn('fora', result.response_text.lower())


# ─── Fluxo 4: Guarda de sessão sem itens ─────────────────────────────────────

class EmptySessionGuardTest(ConversationFlowBase):
    """
    Garante que tentar finalizar o pedido sem itens pendentes
    não cria um pedido vazio e retorna mensagem orientativa.
    """

    def test_pay_pix_with_no_items_returns_error_no_order_created(self):
        handler = self._handler()
        with patch(_PATCH_CREATE_ORDER) as mock_create:
            result = handler.handle({'reply_id': 'pay_pix'})

        mock_create.assert_not_called()
        self.assertIsNotNone(result.response_text)
        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())

    def test_pay_pickup_with_no_items_returns_error_no_order_created(self):
        handler = self._handler()
        with patch(_PATCH_CREATE_ORDER) as mock_create:
            result = handler.handle({'reply_id': 'pay_pickup'})

        mock_create.assert_not_called()
        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())

    def test_delivery_choice_without_items_returns_error(self):
        """order_delivery sem itens deve alertar (não travar com exceção)."""
        handler = self._handler()
        result = handler.handle({'reply_id': 'order_delivery'})
        # Ou retorna erro de itens, ou pede endereço — nunca 500
        self.assertIsNotNone(result)


# ─── Fluxo 5: Intent transacional NÃO usa LLM ────────────────────────────────

class TransactionalIntentNoLLMTest(ConversationFlowBase):
    """
    CREATE_ORDER, INTERACTIVE_REPLY, ORDER_STATUS são transacionais:
    o UnifiedService deve tratá-los no handler, nunca passar para o LLM.
    """

    def test_create_order_intent_is_not_in_consultative_set(self):
        """CREATE_ORDER não deve estar no conjunto de intenções consultivas."""
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertNotIn(IntentType.CREATE_ORDER, UnifiedService.CONSULTATIVE_INTENTS)

    def test_interactive_reply_intent_is_not_in_consultative_set(self):
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertNotIn(IntentType.INTERACTIVE_REPLY, UnifiedService.CONSULTATIVE_INTENTS)

    def test_order_status_intent_is_not_in_consultative_set(self):
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertNotIn(IntentType.ORDER_STATUS, UnifiedService.CONSULTATIVE_INTENTS)


# ─── Fluxo 6: Intent consultivo pode usar LLM ────────────────────────────────

class ConsultativeIntentCanUseLLMTest(ConversationFlowBase):
    """GREETING, PRICE_CHECK, DELIVERY_INFO etc. são consultivos — permitidos ao LLM."""

    def test_greeting_intent_in_consultative_set(self):
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertIn(IntentType.GREETING, UnifiedService.CONSULTATIVE_INTENTS)

    def test_delivery_info_intent_in_consultative_set(self):
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertIn(IntentType.DELIVERY_INFO, UnifiedService.CONSULTATIVE_INTENTS)

    def test_price_check_intent_in_consultative_set(self):
        from apps.automation.services.unified_service import UnifiedService
        from apps.whatsapp.intents.detector import IntentType

        self.assertIn(IntentType.PRICE_CHECK, UnifiedService.CONSULTATIVE_INTENTS)


# ─── Fluxo 7: Stock decrement no pedido final ─────────────────────────────────

class StockDecrementOnOrderTest(ConversationFlowBase):
    """
    Pedido criado via WhatsApp decrementa estoque de produtos com track_stock=True.
    Usa WhatsAppOrderService diretamente (não via handler) para isolar o comportamento.
    """

    def test_tracked_product_stock_decremented_after_order(self):
        tracked = _make_product(
            self.store, 'Produto Monitorado', Decimal('30.00'),
            track_stock=True, stock_quantity=10,
        )
        from apps.whatsapp.services.order_service import WhatsAppOrderService

        svc = WhatsAppOrderService(
            store=self.store,
            phone_number=self.phone,
            customer_name='Cliente',
        )
        with patch(_PATCH_PAYMENT, return_value={'success': True}), \
             patch(_PATCH_BROADCAST), \
             patch.object(svc, '_update_session'):
            result = svc.create_order_from_cart(
                items=[{'product_id': str(tracked.id), 'quantity': 3}],
                delivery_method='pickup',
                payment_method='cash',
            )

        self.assertTrue(result['success'])
        tracked.refresh_from_db()
        self.assertEqual(tracked.stock_quantity, 7)

    def test_untracked_product_stock_unchanged_after_order(self):
        untracked = _make_product(
            self.store, 'Produto Sem Controle', Decimal('30.00'),
            track_stock=False, stock_quantity=0,
        )
        from apps.whatsapp.services.order_service import WhatsAppOrderService

        svc = WhatsAppOrderService(
            store=self.store,
            phone_number=self.phone,
            customer_name='Cliente',
        )
        with patch(_PATCH_PAYMENT, return_value={'success': True}), \
             patch(_PATCH_BROADCAST), \
             patch.object(svc, '_update_session'):
            result = svc.create_order_from_cart(
                items=[{'product_id': str(untracked.id), 'quantity': 5}],
                delivery_method='pickup',
                payment_method='cash',
            )

        self.assertTrue(result['success'])
        untracked.refresh_from_db()
        self.assertEqual(untracked.stock_quantity, 0)


# ─── Fluxo 8: Rastreamento de pedido do site ─────────────────────────────────

class SiteOrderTrackingTest(ConversationFlowBase):
    """
    Pedidos criados no site devem ser localizáveis pelo bot mesmo quando
    o telefone chega em formato normalizado diferente do salvo no pedido.
    """

    def test_detector_routes_realizei_o_pedido_to_track_order(self):
        detector = IntentDetector(use_llm_fallback=False)
        intent = detector.detect_regex('realizei o pedido TEST-FLOW-001')
        self.assertEqual(intent, IntentType.TRACK_ORDER)

    def test_track_order_finds_site_order_by_phone_and_number(self):
        from apps.whatsapp.intents.handlers import TrackOrderHandler

        site_order = StoreOrder.objects.create(
            store=self.store,
            order_number='SITE-TRACK-001',
            customer_phone='5563900000050',
            customer_name='Cliente Site',
            customer_email='site@example.com',
            status='confirmed',
            payment_status='paid',
            subtotal=Decimal('30.00'),
            total=Decimal('30.00'),
            delivery_method='delivery',
            payment_method='pix',
        )

        handler = self._handler(TrackOrderHandler)
        result = handler.handle({
            'original_message': 'realizei o pedido SITE-TRACK-001',
            'entities': {'order_number': 'SITE-TRACK-001'},
        })

        self.assertTrue(result.use_interactive)
        self.assertIn(site_order.order_number, result.interactive_data.get('body', ''))
        button_ids = [button['id'] for button in result.interactive_data.get('buttons', [])]
        self.assertIn(f'track_{site_order.id}', button_ids)
