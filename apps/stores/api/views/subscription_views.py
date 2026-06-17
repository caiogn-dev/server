"""
Endpoint de assinatura SaaS: dono inicia a assinatura (preapproval MercadoPago).
POST /api/v1/stores/{store_slug}/subscribe/  body: {"plan": "pro"}
Retorna {init_point, preapproval_id} — o dono abre o init_point e autoriza o cartão.
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store
from apps.stores.services import subscription_service


class StoreSubscribeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        # Só dono/staff/superuser
        can = (
            store.owner_id == request.user.id
            or store.staff.filter(id=request.user.id).exists()
            or request.user.is_superuser
        )
        if not can:
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        plan = (request.data.get('plan') or '').strip()
        if plan not in ('starter', 'pro', 'premium'):
            return Response({'detail': 'Plano inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        payer_email = (request.user.email or '').strip()
        # back_url precisa ser UMA URL válida (FRONTEND_URL é lista p/ CORS → não usar).
        back_url = f"{getattr(settings, 'BILLING_PANEL_URL', 'https://painel.cardapidex.com.br')}/plano"
        try:
            result = subscription_service.create_subscription(store, plan, payer_email, back_url)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)
