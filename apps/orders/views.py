"""
Orders app API views - Uber delivery endpoints.
"""
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.stores.models import Store, StoreOrder
from apps.core.permissions import user_can_access_store
from apps.orders.services.uber_delivery import UberDeliveryClient
from apps.orders.tasks import create_uber_delivery_request

logger = logging.getLogger(__name__)


def _get_store_for_user(user, store_slug):
    """Resolve a loja e garante que o usuário tem acesso (tenant check)."""
    store = get_object_or_404(Store, slug=store_slug)
    if not user_can_access_store(user, store):
        raise PermissionDenied('Você não tem acesso a esta loja.')
    return store


class CreateDeliveryRequestView(APIView):
    """
    POST /api/v1/stores/{store_slug}/orders/{order_id}/create-delivery-request/
    Create a delivery request on Uber.
    Returns 202 ACCEPTED (task queued).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, store_slug, order_id):
        store = _get_store_for_user(request.user, store_slug)
        order = get_object_or_404(StoreOrder, id=order_id, store=store)
        try:
            # Check order status
            if order.status not in ['confirmed', 'preparing']:
                return Response(
                    {
                        'detail': f'Order must be in "confirmed" or "preparing" status to create delivery. '
                                  f'Current status: {order.status}'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Queue Celery task for Uber delivery
            # Convert UUIDs to strings for Celery serialization
            create_uber_delivery_request.delay(str(order.id), str(store.id))

            logger.info(f'Queued Uber delivery request for order {order.id}')

            return Response(
                {'detail': 'Delivery request queued', 'order_id': str(order.id)},
                status=status.HTTP_202_ACCEPTED
            )

        except Exception as e:
            logger.error(f'Error creating delivery request: {str(e)}')
            return Response(
                {'detail': 'Erro ao criar solicitação de entrega.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DeliveryRequestStatusView(APIView):
    """
    GET /api/v1/stores/{store_slug}/orders/{order_id}/delivery-request-status/
    Poll the status of a delivery request.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, store_slug, order_id):
        store = _get_store_for_user(request.user, store_slug)
        order = get_object_or_404(StoreOrder, id=order_id, store=store)
        try:
            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No delivery request found for this order'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Poll Uber API
            client = UberDeliveryClient()
            status_data = client.poll_delivery_status(order.uber_delivery_request_id)

            return Response(status_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f'Error polling delivery status: {str(e)}')
            return Response(
                {'detail': 'Erro ao consultar status da entrega.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CancelDeliveryRequestView(APIView):
    """
    DELETE /api/v1/stores/{store_slug}/orders/{order_id}/delivery-request/
    Cancel a delivery request.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, store_slug, order_id):
        store = _get_store_for_user(request.user, store_slug)
        order = get_object_or_404(StoreOrder, id=order_id, store=store)
        try:
            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No delivery request found for this order'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Call Uber API to cancel
            client = UberDeliveryClient()
            client.cancel_delivery_request(order.uber_delivery_request_id)

            # Update order
            order.uber_delivery_request_id = None
            order.delivery_provider = 'none'
            order.uber_driver_id = None
            order.uber_driver_name = ''
            order.uber_driver_phone = ''
            order.uber_vehicle_info = ''
            order.uber_eta_minutes = None
            order.save()

            logger.info(f'Cancelled Uber delivery request for order {order.id}')

            return Response(
                {'detail': 'Delivery request cancelled'},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f'Error cancelling delivery request: {str(e)}')
            return Response(
                {'detail': 'Erro ao cancelar solicitação de entrega.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
