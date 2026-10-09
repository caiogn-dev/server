"""Lotes de produção: garantir na hora de imprimir a etiqueta e consultar no painel."""
import uuid as uuid_module

from django.db.models import Q
from django.http import Http404
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import accessible_store_ids, user_can_access_store
from apps.stores.models import Store, StoreLote
from apps.stores.services import lotes as servico


class StoreLoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreLote
        fields = ('id', 'codigo', 'produto_nome', 'product', 'fabricacao', 'validade', 'etiquetas', 'criado_em')


def _loja(identificador):
    identificador = str(identificador or '')
    try:
        uuid_module.UUID(identificador)
        return Store.objects.filter(pk=identificador).first()
    except ValueError:
        return Store.objects.filter(slug=identificador).first()


class StoreLoteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreLoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = StoreLote.objects.filter(store_id__in=accessible_store_ids(self.request.user))
        p = self.request.query_params
        if p.get('store'):
            loja = _loja(p['store'])
            qs = qs.filter(store=loja) if loja else qs.none()
        if p.get('q'):
            qs = qs.filter(Q(codigo__icontains=p['q']) | Q(produto_nome__icontains=p['q']))
        if p.get('de'):
            qs = qs.filter(fabricacao__gte=p['de'])
        if p.get('ate'):
            qs = qs.filter(fabricacao__lte=p['ate'])
        return qs

    @action(detail=False, methods=['post'])
    def garantir(self, request):
        loja = _loja(request.data.get('store'))
        if not loja or not user_can_access_store(request.user, loja):
            raise Http404
        try:
            dias = int(request.data.get('validade_dias') or 0)
        except (TypeError, ValueError):
            dias = 0
        if not 0 < dias <= 3650:
            return Response({'detail': 'Informe a validade em dias.'}, status=400)
        itens = [(i.get('produto'), i.get('quantidade', 0)) for i in (request.data.get('itens') or []) if isinstance(i, dict)]
        return Response({'lotes': servico.garantir_lotes(loja, itens, servico.hoje(), dias)})
