"""
Orders app API views - Uber delivery endpoints.
"""
import logging
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_200_OK
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.stores.models import Store, StoreOrder
from apps.orders.services.uber_delivery import UberDeliveryClient
from apps.orders.tasks import create_uber_delivery_request

logger = logging.getLogger(__name__)


class OrderDeliveryViewSet(viewsets.ViewSet):
    """API endpoints for managing Uber delivery requests."""

    def get_store(self, store_slug):
        """Get store by slug."""
        return get_object_or_404(Store, slug=store_slug)

    def get_order(self, store_slug, order_id):
        """Get order by ID and store slug."""
        store = self.get_store(store_slug)
        return get_object_or_404(StoreOrder, id=order_id, store=store)

    @action(detail=True, methods=['post'], url_path='create-delivery-request')
    def create_delivery_request(self, request, store_slug=None, pk=None):
        """
        POST /api/v1/stores/{store_slug}/orders/{id}/create-delivery-request/
        Create a delivery request on Uber.
        Returns 202 ACCEPTED (task queued).
        """
        try:
            order = self.get_order(store_slug, pk)

            # Check order status
            if order.status not in ['confirmed', 'preparing']:
                return Response(
                    {
                        'detail': f'Order must be in "confirmado" or "preparando" status to create delivery. '
                                  f'Current status: {order.status}'
                    },
                    status=HTTP_400_BAD_REQUEST
                )

            # Queue Celery task
            task = create_uber_delivery_request.delay(
                order_id=order.id,
                store_id=order.store_id,
            )

            logger.info(f"Queued Uber delivery task {task.id} for order {order.id}")

            return Response(
                {
                    'delivery_request_id': None,
                    'status': 'pending',
                    'task_id': str(task.id),
                    'message': 'Delivery request queued'
                },
                status=HTTP_202_ACCEPTED
            )

        except Exception as e:
            logger.error(f"Error creating delivery request: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'], url_path='delivery-request-status')
    def delivery_request_status(self, request, store_slug=None, pk=None):
        """
        GET /api/v1/stores/{store_slug}/orders/{id}/delivery-request-status/
        Poll Uber API for delivery request status.
        """
        try:
            order = self.get_order(store_slug, pk)

            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No Uber delivery request found for this order'},
                    status=HTTP_400_BAD_REQUEST
                )

            # Poll Uber API
            uber_client = UberDeliveryClient()
            status_result = uber_client.poll_delivery_status(
                order.uber_delivery_request_id
            )

            # Update order with driver info if available
            if 'driver' in status_result:
                driver = status_result['driver']
                order.uber_driver_id = driver.get('id', '')
                order.uber_driver_name = driver.get('name', '')
                order.uber_driver_phone = driver.get('phone', '')
                order.uber_vehicle_info = driver.get('vehicle', '')
                order.uber_eta_minutes = driver.get('eta_minutes')
                order.uber_pickup_instructions = driver.get('pickup_instructions', '')
                order.save(
                    update_fields=[
                        'uber_driver_id',
                        'uber_driver_name',
                        'uber_driver_phone',
                        'uber_vehicle_info',
                        'uber_eta_minutes',
                        'uber_pickup_instructions',
                    ]
                )

            return Response(status_result, status=HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error polling delivery status: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['delete'], url_path='delivery-request')
    def cancel_delivery_request(self, request, store_slug=None, pk=None):
        """
        DELETE /api/v1/stores/{store_slug}/orders/{id}/delivery-request/
        Cancel an Uber delivery request.
        """
        try:
            order = self.get_order(store_slug, pk)

            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No Uber delivery request found for this order'},
                    status=HTTP_400_BAD_REQUEST
                )

            # Cancel on Uber
            uber_client = UberDeliveryClient()
            result = uber_client.cancel_delivery_request(
                order.uber_delivery_request_id
            )

            # Clear Uber fields
            order.uber_delivery_request_id = None
            order.uber_driver_id = None
            order.uber_driver_name = ''
            order.uber_driver_phone = ''
            order.uber_vehicle_info = ''
            order.uber_eta_minutes = None
            order.uber_pickup_instructions = ''
            order.delivery_provider = 'none'
            order.save(
                update_fields=[
                    'uber_delivery_request_id',
                    'uber_driver_id',
                    'uber_driver_name',
                    'uber_driver_phone',
                    'uber_vehicle_info',
                    'uber_eta_minutes',
                    'uber_pickup_instructions',
                    'delivery_provider',
                ]
            )

            logger.info(f"Cancelled Uber delivery for order {order.id}")

            return Response(result, status=HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error cancelling delivery: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=HTTP_400_BAD_REQUEST
            )
