"""
Public API views — AllowAny, read-only.
Used by pastita-3d and ce-saladas storefronts (no auth required).

Endpoints:
  GET /api/v1/public/{slug}/                      -> store info
  GET /api/v1/public/{slug}/catalog/              -> full catalog (categories + products)
  GET /api/v1/public/{slug}/categories/           -> categories
  GET /api/v1/public/{slug}/products/             -> products (filterable)
  GET /api/v1/public/{slug}/products/{pk}/        -> product detail
  GET /api/v1/public/{slug}/availability/         -> store open/closed status
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.stores.models import Store, StoreCategory, StoreProduct
from .serializers import (
    PublicStoreSerializer,
    PublicCategorySerializer,
    PublicProductSerializer,
)


class _PublicProductPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


def _get_active_store(slug):
    return get_object_or_404(Store, slug=slug, status='active')


@api_view(['GET'])
@permission_classes([AllowAny])
def public_store_detail(request, slug):
    store = _get_active_store(slug)
    return Response(PublicStoreSerializer(store, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_store_catalog(request, slug):
    """Full catalog: store + categories with their products."""
    store = _get_active_store(slug)

    categories = (
        StoreCategory.objects
        .filter(store=store, is_active=True)
        .prefetch_related('products')
        .order_by('sort_order', 'name')
    )

    catalog = []
    for cat in categories:
        products = cat.products.filter(status='active').order_by('sort_order', 'name')
        if not products.exists():
            continue
        catalog.append({
            **PublicCategorySerializer(cat, context={'request': request}).data,
            'products': PublicProductSerializer(products, many=True, context={'request': request}).data,
        })

    return Response({
        'store': PublicStoreSerializer(store, context={'request': request}).data,
        'catalog': catalog,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def public_store_categories(request, slug):
    store = _get_active_store(slug)
    categories = (
        StoreCategory.objects
        .filter(store=store, is_active=True)
        .order_by('sort_order', 'name')
    )
    return Response(PublicCategorySerializer(categories, many=True, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_store_products(request, slug):
    store = _get_active_store(slug)
    products = (
        StoreProduct.objects
        .filter(store=store, status='active')
        .select_related('category')
        .order_by('sort_order', 'name')
    )

    category_slug = request.query_params.get('category')
    if category_slug:
        products = products.filter(category__slug=category_slug)

    search = request.query_params.get('search')
    if search:
        products = products.filter(name__icontains=search)

    paginator = _PublicProductPagination()
    page = paginator.paginate_queryset(products, request)
    serializer = PublicProductSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_product_detail(request, slug, pk):
    store = _get_active_store(slug)
    product = get_object_or_404(StoreProduct, pk=pk, store=store, status='active')
    return Response(PublicProductSerializer(product, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_store_availability(request, slug):
    """Return whether the store is currently open, plus today's hours."""
    store = _get_active_store(slug)
    now = timezone.now()
    day_name = now.strftime('%A').lower()
    hours = (store.operating_hours or {}).get(day_name)
    return Response({
        'is_open': store.is_open(),
        'today': day_name,
        'hours': hours,
        'operating_hours': store.operating_hours or {},
    })
