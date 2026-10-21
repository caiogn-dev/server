"""Entregadores, ranking da operação e ajudas do cadastro (IA na descrição, combos)."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import user_can_access_store
from apps.stores.models import Entregador, Store, StoreOrder
from apps.stores.services.ranking_da_operacao import ranking_da_operacao


class EntregadorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entregador
        fields = ['id', 'nome', 'telefone', 'is_active']

    def validate_nome(self, valor):
        valor = (valor or '').strip()
        if not valor:
            raise serializers.ValidationError('Informe o nome do entregador.')
        return valor


class _DaLoja(APIView):
    permission_classes = [IsAuthenticated]

    def loja(self, request, store_slug):
        loja = Store.objects.filter(slug=store_slug).first()
        if loja is None or not user_can_access_store(request.user, loja):
            # "Não encontrada" e não "sem permissão": confirmar que a loja
            # existe já é informação sobre o vizinho.
            from django.http import Http404
            raise Http404
        return loja


class EntregadoresView(_DaLoja):
    def get(self, request, store_slug):
        loja = self.loja(request, store_slug)
        return Response(EntregadorSerializer(loja.entregadores.all(), many=True).data)

    def post(self, request, store_slug):
        loja = self.loja(request, store_slug)
        s = EntregadorSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(store=loja)
        return Response(s.data, status=201)


class EntregadorView(_DaLoja):
    def patch(self, request, store_slug, pk):
        loja = self.loja(request, store_slug)
        s = EntregadorSerializer(get_object_or_404(Entregador, pk=pk, store=loja), data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class EntregadorDoPedidoView(_DaLoja):
    """POST {entregador: id | null} — quem levou este pedido."""

    def post(self, request, store_slug, pk):
        loja = self.loja(request, store_slug)
        pedido = get_object_or_404(StoreOrder, pk=pk, store=loja)
        entregador_id = request.data.get('entregador')
        entregador = get_object_or_404(Entregador, pk=entregador_id, store=loja) if entregador_id else None
        pedido.entregador = entregador
        pedido.save(update_fields=['entregador', 'updated_at'])
        return Response({'entregador': str(entregador.id) if entregador else None,
                         'entregador_nome': entregador.nome if entregador else None})


class RankingDaOperacaoView(_DaLoja):
    def get(self, request, store_slug):
        loja = self.loja(request, store_slug)
        try:
            dias = max(1, min(365, int(request.query_params.get('dias', 30))))
        except (TypeError, ValueError):
            dias = 30
        return Response(ranking_da_operacao(loja, dias=dias))


class MelhorarDescricaoView(_DaLoja):
    """POST {nome, descricao, categoria} → sugestão. Nada é gravado aqui."""

    def post(self, request, store_slug):
        from apps.stores.services.descricao_com_ia import IaForaDoAr, SemSugestao, melhorar_descricao

        self.loja(request, store_slug)
        dados = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(melhorar_descricao(
                str(dados.get('nome') or ''), str(dados.get('descricao') or ''), str(dados.get('categoria') or ''),
            ))
        except IaForaDoAr as exc:
            return Response({'error': str(exc)}, status=503)
        except SemSugestao as exc:
            return Response({'error': str(exc)}, status=400)


class SugestaoDeCombosView(_DaLoja):
    def get(self, request, store_slug):
        from apps.stores.services.sugestao_de_combos import sugestao_de_combos

        loja = self.loja(request, store_slug)
        return Response({'sugestoes': sugestao_de_combos(loja)})
