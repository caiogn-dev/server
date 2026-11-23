"""Carteira do cliente: GET/POST /stores/{slug}/customer/cartoes/ e
DELETE /stores/{slug}/customer/cartoes/{card_id}/ (só o final e a bandeira
saem daqui; o cartão mora no Mercado Pago)."""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.services import cartoes_salvos
from apps.stores.api.views.storefront_views import get_active_store


class CartoesDoClienteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        if not cartoes_salvos.disponivel(store):
            return Response({'disponivel': False, 'cartoes': []})
        return Response({'disponivel': True, 'cartoes': cartoes_salvos.listar(request.user)})

    def post(self, request, store_slug):
        store = get_active_store(store_slug)
        if not cartoes_salvos.disponivel(store):
            return Response({'error': 'Esta loja não guarda cartões.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cartao = cartoes_salvos.salvar(request.user, str(request.data.get('token') or ''))
        except cartoes_salvos.CartaoNaoSalvo as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(cartao, status=status.HTTP_201_CREATED)


class CartaoDoClienteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, store_slug, card_id):
        get_active_store(store_slug)
        cartoes_salvos.remover(request.user, card_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
