from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .storefront_views import get_active_store
from ...models import StoreLoyaltyAccount
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
