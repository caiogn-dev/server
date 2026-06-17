"""
Combo API views for storefront and management endpoints.

Provides:
- ComboDetailView: GET /api/v1/stores/{store_slug}/combos/{combo_id}/
- ComboListView: GET /api/v1/stores/{store_slug}/combos/
- AddComboToCartView: POST /api/v1/stores/{store_slug}/cart/add-combo/
"""
import uuid as uuid_module
from rest_framework import views, permissions, status
from rest_framework.response import Response
from django.db import transaction

from apps.stores.models import (
    StoreCombo, StoreCart, StoreCartComboItem, Store
)
from apps.stores.validators import ComboSelectionValidator
from ..serializers import StoreComboSerializer
from .base import filter_by_store


class AddComboToCartView(views.APIView):
    """
    POST /api/v1/stores/{store_slug}/cart/add-combo/

    Add a combo to the customer's cart with validated variant selections.

    Request Body:
    {
        "combo_id": "uuid",
        "quantity": 1,
        "selections": {
            "group_id_1": ["variant_id_1", "variant_id_2"],
            "group_id_2": ["variant_id_3"]
        }
    }

    Validates:
    - Combo belongs to store
    - All selections pass ComboSelectionValidator
    - Stock availability (if tracked)

    Returns:
    - 200: StoreCartComboItem created, returns cart summary
    - 400: Validation errors
    - 404: Combo or store not found
    """
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request, store_slug):
        """Add combo to cart with validated selections."""
        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            return Response(
                {'detail': 'Loja não encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Parse request data
        combo_id = request.data.get('combo_id')
        quantity = request.data.get('quantity', 1)
        selections = request.data.get('selections', {})

        # Validate combo_id format
        if not combo_id:
            return Response(
                {'detail': 'combo_id é obrigatório.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            combo_uuid = uuid_module.UUID(str(combo_id))
        except (ValueError, AttributeError):
            return Response(
                {'detail': 'ID de combo inválido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get combo and verify it belongs to this store
        try:
            combo = StoreCombo.objects.get(id=combo_uuid, store=store)
        except StoreCombo.DoesNotExist:
            return Response(
                {'detail': 'Combo não encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Validate quantity
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Quantidade deve ser um número inteiro positivo.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate selections using ComboSelectionValidator
        validator = ComboSelectionValidator(combo)
        if not validator.validate(selections):
            return Response(
                {'errors': validator.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create cart for this user/session
        cart = self._get_or_create_cart(store, request)

        # Create StoreCartComboItem
        try:
            combo_item = StoreCartComboItem.objects.create(
                cart=cart,
                combo=combo,
                combo_name=combo.name,
                unit_price=combo.compute_unit_price(selections),
                quantity=quantity,
                group_selections=selections,
                customizations={'selections': selections},
            )
        except Exception as e:
            return Response(
                {'detail': f'Erro ao adicionar combo ao carrinho: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Return cart summary
        return Response(
            self._get_cart_response(cart),
            status=status.HTTP_200_OK
        )

    def _get_or_create_cart(self, store, request):
        """Get or create cart based on authentication status."""
        if request.user and request.user.is_authenticated:
            cart, _ = StoreCart.objects.get_or_create(
                store=store,
                user=request.user,
                is_active=True,
                defaults={'metadata': {}}
            )
        else:
            # Prefer the explicit guest cart key used by cardapidex-web, then
            # fall back to Django's session key for older clients.
            session_key = (
                request.headers.get('X-Cart-Key')
                or request.query_params.get('cart_key')
                or request.data.get('cart_key')
            )
            if not session_key:
                session_key = request.session.session_key
            if not session_key:
                try:
                    request.session.create()
                    session_key = request.session.session_key
                except Exception:
                    session_key = f"cart_{uuid_module.uuid4()}"

            cart, _ = StoreCart.objects.get_or_create(
                store=store,
                session_key=str(session_key)[:255],
                user__isnull=True,
                is_active=True,
                defaults={'metadata': {}}
            )
        return cart

    def _get_cart_response(self, cart):
        """Build cart summary response."""
        return {
            'cart_id': str(cart.id),
            'store_id': str(cart.store_id),
            'item_count': cart.item_count,
            'subtotal': str(cart.subtotal),
            'items': [
                {
                    'id': str(item.id),
                    'combo_name': item.effective_name,
                    'quantity': item.quantity,
                    'unit_price': str(item.effective_price),
                    'subtotal': str(item.subtotal),
                    'selections': item.group_selections or item.customizations.get('selections', {})
                }
                for item in cart.combo_items.all()
            ]
        }
