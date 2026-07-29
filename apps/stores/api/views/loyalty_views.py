from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from .storefront_views import get_active_store, PublicWriteThrottle
from ...models import StoreLoyaltyAccount, StoreOrder
from ...services.checkout_service import CheckoutService
from ...services.loyalty_service import LoyaltyService


class LoyaltyStatusView(APIView):
    """GET — returns current loyalty progress for the authenticated user."""
    permission_classes = [IsAuthenticated]

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        loyalty = CheckoutService.get_loyalty_status(store, request.user)
        return Response(loyalty)


class LoyaltyRedeemCheckView(APIView):
    """POST — pre-flight check: confirms user has a reward available to redeem.
    Returns 409 if no reward is available.
    Actual redemption happens at checkout via use_loyalty_reward=True."""
    permission_classes = [IsAuthenticated]

    def post(self, request, store_slug):
        store = get_active_store(store_slug)
        loyalty = CheckoutService.get_loyalty_status(store, request.user)
        if not loyalty.get('can_redeem'):
            return Response(
                {'error': 'Nenhuma recompensa disponível', 'loyalty': loyalty},
                status=409,
            )
        return Response({'success': True, 'loyalty': loyalty})


class LoyaltyAccountsView(APIView):
    """Listagem de contas de fidelidade da loja (dash). Dono ou superuser."""
    permission_classes = [IsAuthenticated]

    PAGE_SIZE = 50

    def get(self, request, store_slug):
        store = get_active_store(store_slug)
        if not (request.user.is_superuser or store.owner_id == request.user.id):
            return Response({'error': 'Sem permissão para esta loja.'}, status=403)
        threshold, _enabled = LoyaltyService._config(store)
        qs = (StoreLoyaltyAccount.objects.filter(store=store)
              .select_related('user').order_by('-updated_at'))
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE
        results = []
        for acc in qs[start:start + self.PAGE_SIZE]:
            earned = acc.qualified_count // threshold
            results.append({
                'user_id': str(acc.user_id),
                'display_name': acc.user.get_full_name() or acc.user.username,
                'email': acc.user.email,
                'qualified_count': acc.qualified_count,
                'redeemed_count': acc.redeemed_count,
                'progress': acc.qualified_count % threshold,
                'available_rewards': max(0, earned - acc.redeemed_count),
                'updated_at': acc.updated_at.isoformat(),
            })
        return Response({'count': qs.count(), 'results': results})


class LoyaltyGuestStatusView(APIView):
    """POST — status de fidelidade para guest (sem login) identificado só por telefone.

    Storefront não tem login real: clientes são guests (useGuestInfo, 90 dias).
    Resolve o usuário pelo último pedido da loja vinculado a esse telefone
    (mesmas variantes usadas pelo bot em LoyaltyStatusHandler) e devolve o
    mesmo formato de status do endpoint autenticado — nunca PII (nome/email).
    """
    permission_classes = [AllowAny]
    throttle_classes = [PublicWriteThrottle]

    @staticmethod
    def _build_phone_variants(raw_phone: str) -> list:
        from apps.core.utils import normalize_phone_number
        raw_phone = raw_phone or ''
        normalized = normalize_phone_number(raw_phone)
        digits_only = ''.join(filter(str.isdigit, raw_phone))
        variants = [raw_phone, normalized, digits_only]
        if normalized:
            variants.append(f'+{normalized}')
        # Autofill (Google/iOS) grava com +55 e pedidos antigos sem — casa os
        # dois sentidos: versão local (sem código do país) e versão com 55.
        if digits_only.startswith('55') and len(digits_only) in (12, 13):
            local = digits_only[2:]
            variants.extend([local, f'+55{local}'])
        elif digits_only and len(digits_only) in (10, 11):
            variants.extend([f'55{digits_only}', f'+55{digits_only}'])
        return [value for value in dict.fromkeys(v for v in variants if v)]

    def _resolve_user(self, store, phone):
        phone_variants = self._build_phone_variants(phone)
        if not phone_variants:
            return None
        order = (StoreOrder.objects
                 .filter(store=store, customer_phone__in=phone_variants, customer__isnull=False)
                 .order_by('-created_at').first())
        return order.customer if order else None

    def post(self, request, store_slug):
        store = get_active_store(store_slug)
        phone = request.data.get('phone') or ''
        user = self._resolve_user(store, phone)
        loyalty = CheckoutService.get_loyalty_status(store, user)
        return Response(loyalty)
