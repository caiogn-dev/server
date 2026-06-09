"""
Combo API views for storefront and management endpoints.

Provides:
- ComboDetailView: GET /api/v1/stores/{store_slug}/combos/{combo_id}/
- ComboListView: GET /api/v1/stores/{store_slug}/combos/
- AddComboToCartView: POST /api/v1/stores/{store_slug}/cart/add-combo/
"""
import uuid as uuid_module
from decimal import Decimal
from rest_framework import views, permissions, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import transaction

from apps.stores.models import (
    StoreCombo, StoreCart, StoreCartComboItem,
    Store
)
from apps.stores.validators import ComboSelectionValidator
from ..serializers import (
    ComboDetailSerializer, ComboListSerializer
)
from .base import filter_by_store


class ComboPagination(PageNumberPagination):
    """Pagination for combo list views."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ComboDetailView(views.APIView):
    """
    GET /api/v1/stores/{store_slug}/combos/{combo_id}/

    Returns full combo details including:
    - Basic info (name, price, image, etc.)
    - Groups with variants and stock info
    - Selection rules per group
    - Per-variant limits

    Enforces tenant isolation: returns 404 if combo.store.slug != store_slug
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, store_slug, combo_id):
        """Retrieve combo details with groups and variants."""
        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            return Response(
                {'detail': 'Loja não encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            combo_uuid = uuid_module.UUID(str(combo_id))
        except (ValueError, AttributeError, TypeError):
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

        serializer = ComboDetailSerializer(combo)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ComboListView(views.APIView):
    """
    GET /api/v1/stores/{store_slug}/combos/?is_active=true

    Lists combos for a store with optional filtering.

    Query Parameters:
    - is_active: Filter by active status (true/false)
    - page: Pagination (default: 1)
    - page_size: Results per page (default: 20, max: 100)
    """
    permission_classes = [permissions.AllowAny]
    pagination_class = ComboPagination

    def get(self, request, store_slug):
        """List combos for store with optional filtering."""
        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            return Response(
                {'detail': 'Loja não encontrada.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Start with combos for this store
        queryset = StoreCombo.objects.filter(store=store).order_by('sort_order', 'name')

        # Optional: filter by is_active
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(is_active=is_active_bool)

        # Paginate
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = ComboListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        # Fallback if no pagination
        serializer = ComboListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
                unit_price=combo.price,
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
