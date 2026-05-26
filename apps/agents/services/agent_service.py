import json
import logging
import uuid
from typing import List, Dict, Any, Optional

from apps.core.exceptions import BaseAPIException
from ..models import Agent, AgentConversation, AgentMessage
from .langchain_service import LangchainService

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent management operations."""

    @staticmethod
    def get_agent_response(
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get response from an agent.

        This is the main entry point for agent interactions.
        """
        try:
            agent = Agent.objects.get(id=agent_id, is_active=True, status=Agent.AgentStatus.ACTIVE)
        except Agent.DoesNotExist:
            raise BaseAPIException("Agente não encontrado ou inativo")

        service = LangchainService(agent)
        return service.process_message(
            message=message,
            session_id=session_id,
            phone_number=phone_number,
            conversation_id=conversation_id
        )

    @staticmethod
    def create_conversation(
        agent_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> AgentConversation:
        """Create a new conversation with an agent."""
        agent = Agent.objects.get(id=agent_id)

        conversation = AgentConversation.objects.create(
            agent=agent,
            user_id=user_id,
            session_id=str(uuid.uuid4()),
            metadata=metadata or {}
        )

        return conversation

    @staticmethod
    def add_message(
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> AgentMessage:
        """Add a message to a conversation."""
        conversation = AgentConversation.objects.get(id=conversation_id)

        message = AgentMessage.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            metadata=metadata or {}
        )

        # Update conversation timestamp
        conversation.save()

        return message

    @staticmethod
    def create_order_from_conversation(
        phone_number: str,
        items: List[Dict[str, Any]],
        customer_name: str = '',
        delivery_address: str = '',
        payment_method: str = 'dinheiro',
        notes: str = '',
        store=None,
        store_slug: str = '',
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an order from WhatsApp conversation.

        Args:
            phone_number: Customer phone number
            items: List of {'product_id': str, 'quantity': int, 'variant_id': str (optional)}
            customer_name: Customer name
            delivery_address: Delivery address
            payment_method: Payment method (dinheiro, pix, cartao)
            notes: Additional notes

        Returns:
            Dict with order details or error
        """
        from apps.stores.models import Store, StoreProduct, StoreCart
        from apps.stores.services.cart_service import cart_service
        from apps.stores.services.checkout_service import CheckoutService
        from apps.users.models import UnifiedUser

        try:
            # Resolve store from explicit arg > slug > conversation.
            if store is None and store_slug:
                store = Store.objects.filter(slug=store_slug).first()
            if store is None and conversation_id:
                try:
                    from apps.conversations.models import Conversation
                    from apps.automation.services.context_service import AutomationContextService
                    conversation = Conversation.objects.select_related('account').get(id=conversation_id)
                    store = AutomationContextService.resolve(conversation=conversation).store
                except Exception:
                    store = None
            if not store:
                return {'success': False, 'error': 'Loja não encontrada'}

            # UnifiedUser is useful for identity metadata, but StoreCart.user expects
            # the Django auth user model, not UnifiedUser.
            unified_user = UnifiedUser.objects.filter(phone_number=phone_number).first()

            # Create cart
            cart = StoreCart.objects.create(
                store=store,
                user=None,
                session_key=str(uuid.uuid4()),
                metadata={
                    'source': 'whatsapp_agent',
                    'phone_number': phone_number,
                },
            )

            # Add items to cart
            for item_data in items:
                product_id = item_data.get('product_id')
                quantity = item_data.get('quantity', 1)
                variant_id = item_data.get('variant_id')

                try:
                    product = StoreProduct.objects.get(id=product_id, store=store)
                    cart_service.add_item(
                        cart=cart,
                        product_id=str(product.id),
                        variant_id=variant_id,
                        quantity=quantity
                    )
                except StoreProduct.DoesNotExist:
                    logger.warning(f"Product {product_id} not found")
                    continue

            if cart.items.count() == 0:
                cart.delete()
                return {'success': False, 'error': 'Nenhum produto válido no pedido'}

            # Prepare customer data
            customer_data = {
                'name': customer_name or (unified_user.name if unified_user else 'Cliente WhatsApp'),
                'phone': phone_number,
                'email': unified_user.email if unified_user and unified_user.email else f"cliente@{store.slug}.com.br"
            }

            # Prepare delivery data
            delivery_data = None
            if delivery_address:
                delivery_data = {
                    'method': 'delivery',
                    'address': {'raw': delivery_address},
                    'notes': notes
                }
            else:
                delivery_data = {'method': 'pickup'}

            # Create order
            order = CheckoutService.create_order(
                cart=cart,
                customer_data=customer_data,
                delivery_data=delivery_data,
                notes=notes
            )

            # Clear cart after order creation
            cart.delete()

            return {
                'success': True,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': float(order.total),
                'status': order.status,
                'payment_status': order.payment_status
            }

        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return {'success': False, 'error': str(e)}
