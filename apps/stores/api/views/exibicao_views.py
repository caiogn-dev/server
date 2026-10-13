"""Exibição do cardápio — painel. Ver services/exibicao_do_cardapio."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.api.views.informativos_views import _loja
from apps.stores.services import exibicao_do_cardapio as servico


class ExibicaoDoCardapioView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(servico.ler(_loja(request)))

    def patch(self, request):
        loja = _loja(request)
        try:
            return Response(servico.salvar(loja, request.data))
        except servico.ExibicaoInvalida as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
