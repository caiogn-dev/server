"""Entregador iFood no modal do pedido: estado, chamar, cancelar."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import StoreOrder
from ..services import entrega_ifood
from apps.core.permissions import accessible_store_ids


def _pedido(request, order_id):
    return StoreOrder.objects.select_related('store').filter(
        id=order_id, store_id__in=accessible_store_ids(request.user),
    ).first()


class EntregaIfoodView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        pedido = _pedido(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        return Response(entrega_ifood.estado(pedido))


class EntregaIfoodChamarView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        pedido = _pedido(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            entrega_ifood.chamar(pedido)
        except entrega_ifood.EntregaIfoodRecusada as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response(entrega_ifood.estado(pedido))


class EntregaIfoodCancelarView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        pedido = _pedido(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            entrega_ifood.cancelar(pedido, str((request.data or {}).get('motivo') or ''))
        except entrega_ifood.EntregaIfoodRecusada as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response(entrega_ifood.estado(pedido))
