"""
Orders app API views - Uber delivery endpoints.
"""
import logging
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.services.uber_delivery import UberDeliveryClient
from apps.orders.tasks import create_uber_delivery_request
from apps.stores.models import Store, StoreOrder
from apps.stores.permissions import has_store_permission

logger = logging.getLogger(__name__)


class CreateDeliveryRequestView(APIView):
    """
    POST /api/v1/stores/{store_slug}/orders/{order_id}/create-delivery-request/
    Create a delivery request on Uber.
    Returns 202 ACCEPTED (task queued).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, store_slug, order_id):
        try:
            store = get_object_or_404(Store, slug=store_slug)

            if not has_store_permission(request.user, store, 'orders'):
                raise PermissionDenied(
                    "Você não tem permissão para criar entregas nesta loja."
                )

            order = get_object_or_404(StoreOrder, id=order_id, store=store)

            if order.status not in ['confirmed', 'preparing']:
                return Response(
                    {
                        'detail': f'Order must be in "confirmed" or "preparing" status to create delivery. '
                                  f'Current status: {order.status}'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            create_uber_delivery_request.delay(order.id)

            logger.info(f'Queued Uber delivery request for order {order.id}')

            return Response(
                {'detail': 'Delivery request queued', 'order_id': str(order.id)},
                status=status.HTTP_202_ACCEPTED
            )

        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f'Error creating delivery request for order {order_id}: {e}')
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
        try:
            store = get_object_or_404(Store, slug=store_slug)

            if not has_store_permission(request.user, store, 'orders'):
                raise PermissionDenied(
                    "Você não tem permissão para consultar entregas nesta loja."
                )

            order = get_object_or_404(StoreOrder, id=order_id, store=store)

            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No delivery request found for this order'},
                    status=status.HTTP_404_NOT_FOUND
                )

            client = UberDeliveryClient()
            status_data = client.poll_delivery_status(order.uber_delivery_request_id)

            return Response(status_data, status=status.HTTP_200_OK)

        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f'Error polling delivery status for order {order_id}: {e}')
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
        try:
            store = get_object_or_404(Store, slug=store_slug)

            if not has_store_permission(request.user, store, 'orders'):
                raise PermissionDenied(
                    "Você não tem permissão para cancelar entregas nesta loja."
                )

            order = get_object_or_404(StoreOrder, id=order_id, store=store)

            if not order.uber_delivery_request_id:
                return Response(
                    {'detail': 'No delivery request found for this order'},
                    status=status.HTTP_404_NOT_FOUND
                )

            client = UberDeliveryClient()
            client.cancel_delivery_request(order.uber_delivery_request_id)

            order.uber_delivery_request_id = None
            order.delivery_provider = None
            order.save()

            logger.info(f'Cancelled Uber delivery request for order {order.id}')

            return Response(
                {'detail': 'Delivery request cancelled'},
                status=status.HTTP_200_OK
            )

        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f'Error cancelling delivery request for order {order_id}: {e}')
            return Response(
                {'detail': 'Erro ao cancelar solicitação de entrega.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
