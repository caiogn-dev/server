"""Informativos da loja (avisos no cardápio) — painel. Ver services/informativos."""
import uuid

from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import accessible_store_ids
from apps.stores.models import Store
from apps.stores.services import informativos as servico


def _loja(request) -> Store:
    pedida = str(request.query_params.get('store') or '').strip()
    if not pedida:
        raise NotFound('Informe a loja (store).')
    filtro = Q(slug=pedida)
    try:
        uuid.UUID(pedida)
        filtro |= Q(id=pedida)
    except ValueError:
        pass
    loja = Store.objects.filter(id__in=accessible_store_ids(request.user)).filter(filtro).first()
    if loja is None:
        raise NotFound('Loja não encontrada.')
    return loja


class InformativosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(servico.listar(_loja(request)))

    def post(self, request):
        loja = _loja(request)
        try:
            return Response(servico.criar(loja, request.data), status=status.HTTP_201_CREATED)
        except servico.InformativoInvalido as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InformativoView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, informativo_id):
        loja = _loja(request)
        try:
            item = servico.editar(loja, informativo_id, request.data)
        except servico.InformativoInvalido as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if item is None:
            raise NotFound('Informativo não encontrado.')
        return Response(item)

    def delete(self, request, informativo_id):
        if not servico.apagar(_loja(request), informativo_id):
            raise NotFound('Informativo não encontrado.')
        return Response(status=status.HTTP_204_NO_CONTENT)
