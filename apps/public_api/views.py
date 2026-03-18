"""
Public API views — AllowAny, read-only.
Used by pastita-3d and ce-saladas storefronts (no auth required).

Endpoints:
  GET /api/v1/public/{slug}/                      -> store info
  GET /api/v1/public/{slug}/catalog/              -> full catalog (categories + products)
  GET /api/v1/public/{slug}/categories/           -> categories
  GET /api/v1/public/{slug}/products/             -> products (filterable)
  GET /api/v1/public/{slug}/products/{pk}/        -> product detail
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from apps.stores.models import Store, StoreCategory, StoreProduct
from .serializers import (
    PublicStoreSerializer,
    PublicCategorySerializer,
    PublicProductSerializer,
)


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

    return Response(PublicProductSerializer(products, many=True, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_product_detail(request, slug, pk):
    store = _get_active_store(slug)
    product = get_object_or_404(StoreProduct, pk=pk, store=store, is_active=True)
    return Response(PublicProductSerializer(product, context={'request': request}).data)
