from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .storefront_views import get_active_store
from ...services.checkout_service import CheckoutService


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
