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
            dados = request.data or {}
            codigo = dados.get('codigo')
            entrega_ifood.cancelar(pedido, str(dados.get('motivo') or ''),
                                   codigo=str(codigo) if codigo not in (None, '') else None)
        except entrega_ifood.EntregaIfoodRecusada as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response(entrega_ifood.estado(pedido))


class EntregaIfoodMotivosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        pedido = _pedido(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        try:
            return Response({'motivos': entrega_ifood.motivos_de_cancelamento(pedido)})
        except entrega_ifood.EntregaIfoodRecusada as exc:
            return Response({'detail': str(exc)}, status=400)


class EntregaIfoodEnderecoView(APIView):
    """Cliente pediu outro endereço: a loja aceita ou recusa."""
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        pedido = _pedido(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido não encontrado.'}, status=404)
        aceitar = (request.data or {}).get('aceitar')
        if not isinstance(aceitar, bool):
            return Response({'detail': 'Envie aceitar: true ou false.'}, status=400)
        try:
            entrega_ifood.responder_endereco(pedido, aceitar)
        except entrega_ifood.EntregaIfoodRecusada as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response(entrega_ifood.estado(pedido))


# ── Pedido QUE VEIO do iFood: cancelar com motivo do iFood e negociação ──

def _pedido_do_ifood(request, order_id):
    from ..services import pedidos_do_ifood
    pedido = _pedido(request, order_id)
    if pedido is None or pedido.source != pedidos_do_ifood.PROVEDOR:
        return None
    return pedido


class PedidoIfoodMotivosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        from ..services import pedidos_do_ifood
        pedido = _pedido_do_ifood(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido do iFood não encontrado.'}, status=404)
        try:
            return Response({'motivos': pedidos_do_ifood.motivos_de_cancelamento(pedido)})
        except pedidos_do_ifood.ErroDoIfood as exc:
            return Response({'detail': str(exc)}, status=400)


class PedidoIfoodCancelarView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        from ..services import pedidos_do_ifood
        pedido = _pedido_do_ifood(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido do iFood não encontrado.'}, status=404)
        dados = request.data or {}
        try:
            pedidos_do_ifood.cancelar_no_ifood(pedido, str(dados.get('codigo') or ''), str(dados.get('detalhe') or ''))
        except pedidos_do_ifood.ErroDoIfood as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response({'status': pedido.status, 'ifood': pedidos_do_ifood.dados_ifood(pedido)})


class PedidoIfoodNegociacaoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        from ..services import pedidos_do_ifood
        pedido = _pedido_do_ifood(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido do iFood não encontrado.'}, status=404)
        return Response({'disputa': pedidos_do_ifood.dados_ifood(pedido).get('disputa')})

    def post(self, request, order_id):
        from ..services import pedidos_do_ifood
        pedido = _pedido_do_ifood(request, order_id)
        if pedido is None:
            return Response({'detail': 'Pedido do iFood não encontrado.'}, status=404)
        d = request.data or {}
        try:
            pedidos_do_ifood.responder_disputa(
                pedido, str(d.get('resposta') or ''), motivo=str(d.get('motivo') or ''),
                detalhe=str(d.get('detalhe') or ''), tipo=str(d.get('tipo') or ''),
                valor_centavos=d.get('valor_centavos'), minutos=d.get('minutos'),
            )
        except (pedidos_do_ifood.ErroDoIfood, ValueError, TypeError) as exc:
            return Response({'detail': str(exc)}, status=400)
        pedido.refresh_from_db()
        return Response({'disputa': pedidos_do_ifood.dados_ifood(pedido).get('disputa')})
