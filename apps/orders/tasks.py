"""
Celery tasks for orders app.
"""
import logging
from django.utils import timezone
from celery import shared_task

from apps.orders.models import StoreOrder
from apps.orders.services.uber_delivery import UberDeliveryClient
from apps.stores.services.delivery_quote_service import delivery_address_text

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def create_uber_delivery_request(self, order_id, store_id):
    """
    Create a delivery request on Uber.
    Retries up to 2 times on failure.
    Args:
        order_id: UUID or str representation of order ID
        store_id: UUID or str representation of store ID
    """
    try:
        order = StoreOrder.objects.select_related('store').get(
            id=order_id,
            store_id=store_id,
        )

        if order.status not in ['confirmed', 'preparing']:
            logger.warning(
                f"Cannot create Uber delivery for order {order_id}: "
                f"status is {order.status}"
            )
            return {'status': 'error', 'message': 'Invalid order status'}

        # Format delivery address
        formatted_address = delivery_address_text(order.delivery_address)

        # Build pickup address with full store location
        pickup_address_parts = [order.store.address]
        if order.store.city:
            pickup_address_parts.append(order.store.city)
        if order.store.state:
            pickup_address_parts.append(order.store.state)
        if order.store.zip_code:
            pickup_address_parts.append(order.store.zip_code)
        pickup_address = ', '.join(filter(None, pickup_address_parts))

        # Call Uber API
        uber_client = UberDeliveryClient()
        result = uber_client.create_delivery_request(
            pickup_address=pickup_address,
            dropoff_address=formatted_address,
            customer_phone=order.customer_phone,
            order_id=order_id,
            items=[
                {
                    'name': item.product_name,
                    'quantity': item.quantity,
                }
                for item in order.items.all()
            ],
        )

        # Store request ID in order
        order.uber_delivery_request_id = result['delivery_request_id']
        order.delivery_provider = 'uber'
        order.uber_created_at = timezone.now()
        order.save(
            update_fields=[
                'uber_delivery_request_id',
                'delivery_provider',
                'uber_created_at',
            ]
        )

        logger.info(
            f"Uber delivery request created for order {order_id}: "
            f"{result['delivery_request_id']}"
        )
        return {'status': 'success', 'delivery_request_id': result['delivery_request_id']}

    except StoreOrder.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return {'status': 'error', 'message': 'Order not found'}
    except Exception as exc:
        logger.error(f"Error creating Uber delivery: {str(exc)}")
        # Retry after 10 seconds
        raise self.retry(exc=exc, countdown=10)
