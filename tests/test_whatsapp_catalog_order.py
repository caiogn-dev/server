from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, CustomerSession
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.services.order_service import WhatsAppOrderService
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.services.webhook_service import WebhookService


User = get_user_model()


class WhatsAppCatalogOrderTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='catalog_owner',
            email='catalog@example.com',
            password='testpass',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Catalog Store',
            slug='catalog-store',
            status=Store.StoreStatus.ACTIVE,
            delivery_enabled=True,
            pickup_enabled=True,
        )
        self.profile, _ = CompanyProfile.objects.get_or_create(
            store=self.store,
            defaults={'company_name': 'Catalog Store'},
        )
        self.account = WhatsAppAccount.objects.create(
            name='Catalog WhatsApp',
            phone_number_id='catalog-phone-id',
            waba_id='catalog-waba',
            phone_number='556399999999',
            access_token_encrypted='fake',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
            owner=self.owner,
        )
        self.conversation = Conversation.objects.create(
            account=self.account,
            phone_number='556388888888',
            contact_name='Cliente Catalogo',
            status=Conversation.ConversationStatus.OPEN,
        )
        self.product_a = StoreProduct.objects.create(
            store=self.store,
            name='Produto A',
            slug='produto-a',
            price=Decimal('10.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
            is_active=True,
        )
        self.product_b = StoreProduct.objects.create(
            store=self.store,
            name='Produto B',
            slug='produto-b',
            price=Decimal('20.00'),
            status=StoreProduct.ProductStatus.ACTIVE,
            is_active=True,
        )

    def test_catalog_order_builds_deterministic_delivery_prompt_and_session_items(self):
        message = Message.objects.create(
            account=self.account,
            conversation=self.conversation,
            whatsapp_message_id='wamid.catalog.order',
            direction=Message.MessageDirection.INBOUND,
            message_type=Message.MessageType.ORDER,
            status=Message.MessageStatus.DELIVERED,
            from_number=self.conversation.phone_number,
            to_number=self.account.phone_number,
            text_body='Order with 2 item(s)',
            content={
                'order': {
                    'catalog_id': 'meta-catalog-id',
                    'product_items': [
                        {
                            'product_retailer_id': str(self.product_a.id),
                            'quantity': 2,
                            'item_price': 10.0,
                            'currency': 'BRL',
                        },
                        {
                            'product_retailer_id': str(self.product_b.id),
                            'quantity': 1,
                            'item_price': 17.5,
                            'currency': 'BRL',
                        },
                    ],
                },
            },
        )

        response = WebhookService()._build_catalog_order_response(
            event=SimpleNamespace(account=self.account),
            message=message,
            company_profile=self.profile,
            store=self.store,
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.interactive_type, 'buttons')
        self.assertEqual(response.metadata['intent'], 'catalog_order')
        self.assertIn('Total dos itens: *R$ 37.50*', response.content)
        self.assertEqual(
            response.interactive_data['buttons'],
            [
                {'id': 'order_delivery', 'title': '🛵 Entrega'},
                {'id': 'order_pickup', 'title': '🏪 Retirada'},
            ],
        )

        session = CustomerSession.objects.get(
            company=self.profile,
            phone_number=self.conversation.phone_number,
        )
        self.assertEqual(
            session.cart_data['pending_items'],
            [
                {
                    'product_id': str(self.product_a.id),
                    'quantity': 2,
                    'unit_price': 10.0,
                    'price_source': 'whatsapp_catalog',
                },
                {
                    'product_id': str(self.product_b.id),
                    'quantity': 1,
                    'unit_price': 17.5,
                    'price_source': 'whatsapp_catalog',
                },
            ],
        )

    @patch('apps.whatsapp.services.order_service.CheckoutService.create_payment')
    @patch('apps.whatsapp.services.order_service.broadcast_order_event')
    def test_whatsapp_catalog_unit_price_is_used_when_order_is_created(self, _broadcast, payment_mock):
        payment_mock.return_value = {'success': True, 'pix_code': 'pix-code'}

        result = WhatsAppOrderService(
            store=self.store,
            phone_number=self.conversation.phone_number,
            customer_name=self.conversation.contact_name,
        ).create_order_from_cart(
            items=[
                {
                    'product_id': str(self.product_b.id),
                    'quantity': 2,
                    'unit_price': 17.5,
                    'price_source': 'whatsapp_catalog',
                },
            ],
            delivery_method='pickup',
            payment_method='pix',
        )

        self.assertTrue(result['success'])
        order = StoreOrder.objects.get(id=result['order'].id)
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal('17.5'))
        self.assertEqual(item.subtotal, Decimal('35.0'))
        self.assertEqual(order.subtotal, Decimal('35.0'))
        self.assertEqual(order.total, Decimal('35.0'))
