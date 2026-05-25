"""
Public API views — AllowAny, read-only.
Used by pastita-3d and ce-saladas storefronts (no auth required).

Endpoints:
  GET  /api/v1/public/{slug}/                      -> store info
  GET  /api/v1/public/{slug}/catalog/              -> full catalog (categories + products)
  GET  /api/v1/public/{slug}/categories/           -> categories
  GET  /api/v1/public/{slug}/products/             -> products (filterable)
  GET  /api/v1/public/{slug}/products/{pk}/        -> product detail
  GET  /api/v1/public/{slug}/availability/         -> store open/closed status
  POST /api/v1/public/leads/                       -> lead capture from /cadastro page
"""
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import AnonRateThrottle


class _PublicReadThrottle(AnonRateThrottle):
    scope = 'public_read'
from django.shortcuts import get_object_or_404
from django.utils import timezone
import logging
from django.conf import settings
from apps.stores.models import Store, StoreCategory, StoreProduct
from .models import Lead
from .serializers import (
    PublicStoreSerializer,
    PublicCategorySerializer,
    PublicProductSerializer,
    LeadSerializer,
)

logger = logging.getLogger(__name__)


class _PublicProductPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


def _get_active_store(slug):
    return get_object_or_404(Store, slug=slug, status='active')


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_detail(request, slug):
    store = _get_active_store(slug)
    return Response(PublicStoreSerializer(store, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
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
@throttle_classes([_PublicReadThrottle])
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
@throttle_classes([_PublicReadThrottle])
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
@throttle_classes([_PublicReadThrottle])
def public_product_detail(request, slug, pk):
    store = _get_active_store(slug)
    product = get_object_or_404(StoreProduct, pk=pk, store=store, status='active')
    return Response(PublicProductSerializer(product, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
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


class _LeadThrottle(AnonRateThrottle):
    scope = 'lead_create'


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def store_by_domain(request):
    """
    Resolve a custom domain to a store config.
    GET /api/v1/public/store-by-domain/?domain=cesaladas.com.br
    Returns 400 if ?domain is missing, 404 if not found or inactive.
    """
    domain = request.query_params.get('domain', '').strip()
    if not domain:
        return Response({'detail': 'Parâmetro domain é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

    # Strip port (e.g. cesaladas.com.br:3000 → cesaladas.com.br)
    domain = domain.split(':')[0].strip()

    store = Store.objects.filter(custom_domain=domain, status='active').first()
    if not store:
        return Response({'detail': 'Loja não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

    return Response(PublicStoreSerializer(store, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([_LeadThrottle])
def create_lead(request):
    """Receive a lead from the /cadastro public page and notify the owner via WhatsApp."""
    serializer = LeadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    lead = serializer.save()
    _notify_owner_whatsapp(lead)
    return Response({'detail': 'Recebemos seu cadastro! Entraremos em contato em breve.'}, status=status.HTTP_201_CREATED)


def _notify_owner_whatsapp(lead: Lead) -> None:
    owner_phone = getattr(settings, 'OWNER_NOTIFICATION_PHONE', '').strip()
    if not owner_phone:
        logger.info('OWNER_NOTIFICATION_PHONE not set — skipping WhatsApp notification for lead %s', lead.id)
        return
    try:
        from apps.whatsapp.utils import get_default_whatsapp_account
        from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
        account = get_default_whatsapp_account()
        if not account:
            logger.warning('No default WhatsApp account — cannot notify owner for lead %s', lead.id)
            return
        svc = WhatsAppAPIService(account)
        business = f' ({lead.business_type})' if lead.business_type else ''
        city = f' — {lead.city}' if lead.city else ''
        msg = (
            f'🚀 *Novo lead no Pastita!*\n\n'
            f'👤 *Nome:* {lead.name}\n'
            f'📱 *WhatsApp:* {lead.phone}\n'
            f'📧 *E-mail:* {lead.email or "—"}\n'
            f'📍 *Cidade:* {lead.city or "—"}\n'
            f'🏪 *Tipo de negócio:* {lead.business_type or "—"}\n'
            f'💬 *Mensagem:* {lead.message or "—"}'
        )
        svc.send_text_message(to=owner_phone, text=msg)
        logger.info('Owner WhatsApp notification sent for lead %s', lead.id)
    except Exception as exc:
        logger.error('Failed to send WhatsApp notification for lead %s: %s', lead.id, exc)
