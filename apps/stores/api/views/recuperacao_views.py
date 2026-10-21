"""O painel do recuperador de vendas."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import user_can_access_store
from apps.stores.models import Store
from apps.stores.services.recuperacao import painel_de_recuperacao


class RecuperacaoDeVendasView(APIView):
    """Quanto ficou no carrinho, quanto voltou e quanto está na mesa.

    A conta mora em `services/recuperacao.py`; aqui só resolve a loja, o
    período e as contas de WhatsApp (para contar os lembretes enviados).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, store_slug):
        loja = Store.objects.filter(slug=store_slug).first()
        if loja is None or not user_can_access_store(request.user, loja):
            # "Não encontrada" e não "sem permissão": confirmar que a loja
            # existe já é informação sobre o vizinho.
            return Response({'detail': 'Loja não encontrada'}, status=404)

        try:
            dias = max(1, min(365, int(request.query_params.get('dias', 30))))
        except (TypeError, ValueError):
            dias = 30

        contas = list(
            Store.objects.filter(pk=loja.pk)
            .exclude(whatsapp_account=None)
            .values_list('whatsapp_account_id', flat=True)
        )

        agora = timezone.now()
        painel = painel_de_recuperacao([loja.id], dias=dias, account_ids=contas, agora=agora)
        # A mesma janela, logo antes: "R$ 380 recuperados" só vira decisão
        # comparado com o mês anterior (do admin do Prefiro).
        antes = painel_de_recuperacao(
            [loja.id], dias=dias, account_ids=contas, agora=agora - timedelta(days=dias),
        )
        painel['anterior'] = {
            chave: antes[chave]
            for chave in ('abandonados', 'valor_abandonado', 'recuperados', 'valor_recuperado', 'taxa_de_recuperacao')
            if chave in antes
        }
        return Response(painel)
