"""
Endpoints de assinatura SaaS:
  POST /api/v1/stores/{store_slug}/subscribe/           → inicia assinatura (preapproval MP)
  GET  /api/v1/stores/{store_slug}/subscription/        → status da assinatura
  POST /api/v1/stores/{store_slug}/subscription/cancel/ → cancela assinatura
  POST /api/v1/stores/{store_slug}/subscription/change-plan/ → troca de plano
  POST/DELETE /api/v1/stores/{store_slug}/subscription/adicionais/ → contrata/cancela adicional
  GET  /api/v1/stores/{store_slug}/invoices/            → lista faturas PIX (subpix:)
  GET  /api/v1/stores/{store_slug}/invoices/current/    → fatura vigente (gera se necessário)
"""
import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.stores import billing
from apps.stores.models import Store, StorePayment, StoreSubscription
from apps.stores.services import subscription_service
from apps.core.permissions import user_can_access_store


def _can_manage(store, user):
    """Retorna True se o usuário pode gerenciar a assinatura da loja.

    is_superuser NÃO entra: a conta do dono da plataforma não assina, cancela
    nem troca o plano da loja de um cliente.
    """
    return user_can_access_store(user, store)


def _adicionais_payload(store):
    """`adicionais`: o que a loja pode usar. `adicionais_inclusos`: o que ela
    tem sem pagar (grandfather) — a tela mostra "incluso" em vez de cancelar."""
    return {
        'adicionais': billing.adicionais_da_loja(store),
        'adicionais_inclusos': list(billing.ADICIONAIS) if billing.is_billing_exempt(store) else [],
    }


class StoreSubscribeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        plan = (request.data.get('plan') or '').strip()
        if plan not in ('starter', 'pro', 'premium'):
            return Response({'detail': 'Plano inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        # Ciclo: o backend sabia cobrar no ano desde sempre, mas este endpoint
        # nunca leu o campo — saía preapproval MENSAL em qualquer caso. Por
        # isso o seletor Mensal/Anual foi tirado da tela em 21/09: prometia
        # "2 meses grátis" e entregava mensal.
        ciclo = (request.data.get('billing_cycle') or 'monthly').strip()
        if ciclo not in ('monthly', 'annual'):
            return Response(
                {'detail': 'Escolha mensal ou anual.'}, status=status.HTTP_400_BAD_REQUEST,
            )

        if ciclo == 'annual':
            # Anual é fatura PIX única, não cartão recorrente.
            try:
                resultado = subscription_service.assinar_no_anual(store, plan)
            except subscription_service.SubscriptionError as e:
                logger.error('Erro no anual (store=%s, plan=%s): %s', store_slug, plan, e)
                return Response(
                    {'detail': 'Erro ao criar assinatura.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(resultado, status=status.HTTP_201_CREATED)

        payer_email = (request.user.email or '').strip()
        back_url = f"{getattr(settings, 'BILLING_PANEL_URL', 'https://painel.cardapidex.com.br')}/plano"
        try:
            result = subscription_service.create_subscription(
                store, plan, payer_email, back_url, billing_cycle=ciclo,
            )
        except subscription_service.SubscriptionError as e:
            logger.error('Erro ao criar assinatura (store=%s, plan=%s): %s', store_slug, plan, e)
            return Response({'detail': 'Erro ao criar assinatura.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class StoreSubscriptionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        sub = StoreSubscription.objects.filter(store=store).first()
        if not sub:
            # Grandfather costuma não ter assinatura e mesmo assim tem os
            # adicionais — a tela precisa saber disso para não oferecê-los.
            return Response(
                {'status': 'none', **_adicionais_payload(store)}, status=status.HTTP_200_OK,
            )

        return Response({
            'plan': sub.plan,
            'status': sub.status,
            'current_period_end': sub.current_period_end,
            'setup_fee_paid': sub.setup_fee_paid,
            'grace_until': sub.grace_until,
            'downgraded_for_nonpayment': sub.downgraded_for_nonpayment,
            **_adicionais_payload(store),
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
            logger.error('Erro ao cancelar assinatura (store=%s): %s', store_slug, e)
            return Response({'detail': 'Erro ao cancelar assinatura.'}, status=status.HTTP_400_BAD_REQUEST)
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
            logger.error('Erro ao trocar plano (store=%s, plan=%s): %s', store_slug, new_plan, e)
            return Response({'detail': 'Erro ao trocar plano de assinatura.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class StoreSubscriptionAdicionaisView(APIView):
    """Contrata (POST) ou cancela (DELETE) um adicional: {"adicional": "<chave>"}.

    Não cobra na hora: o valor entra na próxima fatura da assinatura
    (`billing.valor_dos_adicionais`). Por isso exige assinatura viva — sem
    ela não existe fatura, e o adicional sairia de graça.
    """

    permission_classes = [permissions.IsAuthenticated]
    ASSINATURA_VIVA = (
        StoreSubscription.Status.TRIALING,
        StoreSubscription.Status.ACTIVE,
        StoreSubscription.Status.PAST_DUE,
    )

    def _preparar(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return None, None, None, Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)
        chave = (request.data.get('adicional') or '').strip()
        if chave not in billing.ADICIONAIS:
            return None, None, None, Response({'detail': 'Adicional inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        if billing.is_billing_exempt(store):
            return None, None, None, Response(
                {'detail': 'Sua loja já tem este adicional incluso.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub = StoreSubscription.objects.filter(store=store).first()
        return store, sub, chave, None

    def post(self, request, store_slug):
        store, sub, chave, erro = self._preparar(request, store_slug)
        if erro:
            return erro
        if not sub or sub.status not in self.ASSINATURA_VIVA:
            return Response(
                {'detail': 'Assine um plano para contratar o adicional.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if chave in (sub.adicionais or {}):
            return Response({'adicionais': billing.adicionais_da_loja(store)})
        sub.adicionais = {
            **(sub.adicionais or {}),
            chave: {'contratado_em': timezone.now().isoformat(), 'implantacao_quitada': False},
        }
        sub.save(update_fields=['adicionais', 'updated_at'])
        logger.info('Adicional %s contratado p/ loja %s', chave, store.slug)
        return Response(
            {'adicionais': billing.adicionais_da_loja(store)}, status=status.HTTP_201_CREATED,
        )

    def delete(self, request, store_slug):
        store, sub, chave, erro = self._preparar(request, store_slug)
        if erro:
            return erro
        if sub and chave in (sub.adicionais or {}):
            sub.adicionais = {k: v for k, v in sub.adicionais.items() if k != chave}
            sub.save(update_fields=['adicionais', 'updated_at'])
            logger.info('Adicional %s cancelado p/ loja %s', chave, store.slug)
        return Response({'adicionais': billing.adicionais_da_loja(store)})


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
