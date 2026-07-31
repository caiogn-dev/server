"""Avaliação de pedido — endpoint público via access_token + listagem do lojista."""
from rest_framework import permissions, serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from django.db import transaction
from django.http import Http404
from apps.core.permissions import user_can_access_store
from apps.stores.models import Store, StoreOrder, StoreProductReview, StoreReview
from .base import IsStoreOwnerOrStaff

# Pedido só pode ser avaliado depois de chegar ao cliente
REVIEWABLE_STATUSES = ('delivered', 'completed')


class StoreProductReviewItemSerializer(serializers.ModelSerializer):
    """Nota individual de um produto do pedido (mockup 'avaliações por produto')."""

    class Meta:
        model = StoreProductReview
        fields = ['product', 'rating']


class StoreReviewSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    items = StoreProductReviewItemSerializer(many=True, required=False)

    class Meta:
        model = StoreReview
        fields = [
            'id', 'order', 'order_number', 'rating', 'comment',
            'customer_name', 'is_public', 'created_at', 'items',
        ]
        read_only_fields = ['id', 'order', 'is_public', 'created_at']


class _ReviewWriteThrottle(AnonRateThrottle):
    scope = 'review_create'
    rate = '10/hour'


class OrderReviewByTokenView(APIView):
    """GET/POST /api/v1/stores/orders/by-token/{access_token}/review/ (AllowAny)."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [_ReviewWriteThrottle]

    def _get_order(self, access_token):
        try:
            return StoreOrder.objects.select_related('store').get(access_token=access_token)
        except StoreOrder.DoesNotExist:
            return None

    def get(self, request, access_token):
        order = self._get_order(access_token)
        if not order:
            return Response({'detail': 'Pedido não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        review = getattr(order, 'review', None)
        if not review:
            return Response({'detail': 'Pedido ainda não avaliado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(StoreReviewSerializer(review).data)

    def post(self, request, access_token):
        order = self._get_order(access_token)
        if not order:
            return Response({'detail': 'Pedido não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status not in REVIEWABLE_STATUSES:
            return Response(
                {'detail': 'O pedido só pode ser avaliado após a entrega.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(order, 'review'):
            return Response(
                {'detail': 'Este pedido já foi avaliado.'},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = StoreReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Notas por produto: só itens que realmente estão no pedido, sem repetição.
        items = serializer.validated_data.pop('items', [])
        order_product_ids = {
            pid for pid in order.items.values_list('product_id', flat=True) if pid
        }
        seen = set()
        for item in items:
            pid = item['product'].id
            if pid in seen:
                return Response(
                    {'detail': 'Produto repetido na avaliação.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen.add(pid)
            if pid not in order_product_ids:
                return Response(
                    {'detail': 'Só é possível avaliar produtos deste pedido.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            review = serializer.save(store=order.store, order=order)
            StoreProductReview.objects.bulk_create([
                StoreProductReview(review=review, product=item['product'], rating=item['rating'])
                for item in items
            ])
        return Response(StoreReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class StoreReviewListView(ListAPIView):
    """GET /api/v1/stores/{store_slug}/reviews/ — listagem autenticada do lojista."""

    serializer_class = StoreReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]

    def get_queryset(self):
        store = Store.objects.filter(slug=self.kwargs['store_slug']).first()
        if not store or not user_can_access_store(self.request.user, store):
            # 404 para não revelar se a loja existe (info-hiding, mesmo padrão das cash views).
            # IsStoreOwnerOrStaff.has_permission() não verifica ownership quando o kwarg é
            # store_slug em vez de store_pk, portanto o gate precisa ser explícito aqui.
            raise Http404
        qs = StoreReview.objects.filter(store=store).select_related('order')
        rating = self.request.query_params.get('rating')
        if rating:
            qs = qs.filter(rating=rating)
        return qs
