"""
Celery tasks for orders app.
"""
import logging
from django.utils import timezone
from celery import shared_task

from apps.orders.models import StoreOrder
from apps.orders.services.uber_delivery import UberDeliveryClient

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def create_uber_delivery_request(self, order_id: int, store_id: int):
    """
    Create a delivery request on Uber.
    Retries up to 2 times on failure.
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

        # Call Uber API
        uber_client = UberDeliveryClient()
        result = uber_client.create_delivery_request(
            pickup_address=order.store.address,
            dropoff_address=order.delivery_address,
            customer_phone=order.customer_phone,
            order_id=order_id,
            items=[
                {
                    'name': item.product.name,
                    'qty': item.quantity,
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
