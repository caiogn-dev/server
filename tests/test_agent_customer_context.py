from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import Agent
from apps.agents.services import LangchainService
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreCustomer, StoreOrder, StoreOrderItem
from apps.whatsapp.models import WhatsAppAccount


User = get_user_model()


class AgentCustomerContextTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ctx_owner',
            email='ctx-owner@example.com',
            password='testpass',
        )
        self.customer = User.objects.create_user(
            username='gabriel_customer',
            email='5563999547790@pastita.local',
            password='testpass',
            first_name='Gabriel',
            last_name='Gonçalves Nascimento',
        )
        self.store = Store.objects.create(
            owner=self.owner,
            name='Cê Saladas',
            slug='ce-saladas-context',
            status='active',
            is_active=True,
            delivery_enabled=True,
            pickup_enabled=True,
        )
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas',
            phone_number_id='ctx-phone-id',
            waba_id='ctx-waba',
            phone_number='556399999999',
            access_token_encrypted='fake',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
            owner=self.owner,
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account', 'updated_at'])
        self.conversation = Conversation.objects.create(
            account=self.account,
            phone_number='5563999547790',
            contact_name='',
            status=Conversation.ConversationStatus.OPEN,
        )
        StoreCustomer.objects.create(
            store=self.store,
            user=self.customer,
            phone='5563999547790',
            whatsapp='5563999547790',
            addresses=[{
                'tag': 'casa',
                'street': 'Quadra 112 Sul Rua SR 2',
                'number': '4',
                'city': 'Palmas',
                'state': 'TO',
                'zip_code': '77001970',
            }],
        )
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer=self.customer,
            customer_name='Gabriel Gonçalves Nascimento',
            customer_email='5563999547790@pastita.local',
            customer_phone='63999547790',
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
            subtotal=Decimal('48.90'),
            delivery_fee=Decimal('9.00'),
            total=Decimal('57.90'),
            delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
            delivery_address={
                'street': 'Quadra 112 Sul Rua SR 2',
                'number': '4',
                'neighborhood': 'Arse',
                'city': 'Palmas',
                'state': 'TO',
                'zip_code': '77001970',
            },
        )
        StoreOrderItem.objects.create(
            order=self.order,
            product_name='Magnífico Camarão',
            unit_price=Decimal('48.90'),
            quantity=1,
            subtotal=Decimal('48.90'),
        )
        self.agent = Agent.objects.create(
            name='Ctx Agent',
            provider=Agent.AgentProvider.OPENAI,
            model_name='gpt-test',
            status=Agent.AgentStatus.ACTIVE,
            is_active=True,
            system_prompt='Atenda o cliente.',
        )
        self.agent.accounts.add(self.account)

    def test_dynamic_context_includes_customer_identity_history_items_and_address(self):
        service = LangchainService.__new__(LangchainService)
        service.agent = self.agent

        context = service._build_dynamic_context(
            phone_number='5563999547790',
            conversation_id=str(self.conversation.id),
        )

        self.assertIn('CONTEXTO DO CLIENTE', context)
        self.assertIn('Gabriel Gonçalves Nascimento', context)
        self.assertIn('Total de pedidos encontrados: 1', context)
        self.assertIn('Magnífico Camarão', context)
        self.assertIn('Quadra 112 Sul Rua SR 2', context)
        self.assertIn('Nunca trate pedido antigo como pedido atual', context)

    def test_order_history_uses_phone_variants(self):
        service = LangchainService.__new__(LangchainService)
        service.agent = self.agent

        context = service._build_customer_context(
            phone_number='5563999547790',
            conversation_id=str(self.conversation.id),
            store=self.store,
        )

        self.assertIn(self.order.order_number, context)
        self.assertIn('63999547790', context)

    def test_store_name_order_does_not_override_customer_name(self):
        StoreOrder.objects.create(
            store=self.store,
            customer=self.customer,
            customer_name='Cê Saladas',
            customer_email='cliente@ce-saladas.com.br',
            customer_phone='63999547790',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
            subtotal=Decimal('10.00'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('10.00'),
            delivery_method=StoreOrder.DeliveryMethod.PICKUP,
        )
        service = LangchainService.__new__(LangchainService)
        service.agent = self.agent

        context = service._build_customer_context(
            phone_number='5563999547790',
            conversation_id=str(self.conversation.id),
            store=self.store,
        )

        self.assertIn('Nome provável: Gabriel Gonçalves Nascimento', context)
        self.assertNotIn('Nome provável: Cê Saladas', context)
