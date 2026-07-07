"""
Endpoints de assinatura SaaS:
  POST /api/v1/stores/{store_slug}/subscribe/           → inicia assinatura (preapproval MP)
  GET  /api/v1/stores/{store_slug}/subscription/        → status da assinatura
  POST /api/v1/stores/{store_slug}/subscription/cancel/ → cancela assinatura
  POST /api/v1/stores/{store_slug}/subscription/change-plan/ → troca de plano
  GET  /api/v1/stores/{store_slug}/invoices/            → lista faturas PIX (subpix:)
  GET  /api/v1/stores/{store_slug}/invoices/current/    → fatura vigente (gera se necessário)
"""
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store, StorePayment, StoreSubscription
from apps.stores.services import subscription_service


def _can_manage(store, user):
    """Retorna True se o usuário pode gerenciar a assinatura da loja."""
    return (
        store.owner_id == user.id
        or store.staff.filter(id=user.id).exists()
        or user.is_superuser
    )


class StoreSubscribeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        plan = (request.data.get('plan') or '').strip()
        if plan not in ('starter', 'pro', 'premium'):
            return Response({'detail': 'Plano inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        payer_email = (request.user.email or '').strip()
        back_url = f"{getattr(settings, 'BILLING_PANEL_URL', 'https://painel.cardapidex.com.br')}/plano"
        try:
            result = subscription_service.create_subscription(store, plan, payer_email, back_url)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class StoreSubscriptionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        sub = StoreSubscription.objects.filter(store=store).first()
        if not sub:
            return Response({'status': 'none'}, status=status.HTTP_200_OK)

        return Response({
            'plan': sub.plan,
            'status': sub.status,
            'current_period_end': sub.current_period_end,
            'setup_fee_paid': sub.setup_fee_paid,
            'grace_until': sub.grace_until,
            'downgraded_for_nonpayment': sub.downgraded_for_nonpayment,
        })


class StoreSubscriptionCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            sub = subscription_service.cancel_subscription(store)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': sub.status})


class StoreSubscriptionChangePlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        new_plan = (request.data.get('plan') or '').strip()
        payer_email = (request.user.email or '').strip()
        back_url = f"{getattr(settings, 'BILLING_PANEL_URL', 'https://painel.cardapidex.com.br')}/assinatura"
        try:
            result = subscription_service.change_plan(store, new_plan, payer_email, back_url)
        except subscription_service.SubscriptionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


def _invoice_dict(p):
    meta = p.metadata or {}
    return {
        'id': p.payment_id,
        'amount': float(p.amount),
        'status': p.status,
        'kind': meta.get('kind'),
        'pix_code': p.qr_code,
        'pix_qr_code': p.qr_code_base64,
        'ticket_url': p.ticket_url,
        'expires_at': p.expires_at,
        'period_key': meta.get('period_key'),
        'paid_at': p.paid_at,
    }


class StoreInvoiceListView(APIView):
    """GET /api/v1/stores/{store_slug}/invoices/ — lista faturas de assinatura (subpix:) da loja."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        qs = StorePayment.objects.filter(
            store=store, external_reference__startswith='subpix:',
        ).order_by('-created_at')
        return Response({'invoices': [_invoice_dict(p) for p in qs]})


class StoreInvoiceCurrentView(APIView):
    """GET /api/v1/stores/{store_slug}/invoices/current/ — fatura vigente (gera se ainda não existir)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        sub = StoreSubscription.objects.filter(store=store).first()
        if not sub:
            return Response({'invoice': None})

        from apps.stores.services import pix_billing_service
        invoice = pix_billing_service.generate_invoice(sub)  # idempotente; None se isenta
        return Response({'invoice': _invoice_dict(invoice) if invoice else None})
