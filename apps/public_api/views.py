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
from django.db.models import Prefetch
import logging
from decimal import Decimal
from django.conf import settings
from apps.stores.models import Store, StoreCategory, StoreProduct, StoreCombo, StoreProductVariant
from .models import Lead
from .cache import cache_publico, nunca_cachear
from .serializers import (
    PublicStoreSerializer,
    PublicCategorySerializer,
    PublicProductSerializer,
    PublicComboSerializer,
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
def store_by_domain(request):
    domain = request.query_params.get('domain', '').strip()
    if not domain:
        return Response({'error': 'Parâmetro domain é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
    domain = domain.split(':')[0]  # strip port
    store = get_object_or_404(Store, custom_domain=domain, status='active')
    return Response(PublicStoreSerializer(store, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_detail(request, slug):
    store = _get_active_store(slug)
    return Response(PublicStoreSerializer(store, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_bio(request, slug):
    """Payload público da página Link na Bio: store branding + links resolvidos."""
    from apps.stores.models import BioClickStat
    from . import bio as bio_mod
    store = _get_active_store(slug)
    BioClickStat.bump(store, 'page:view')
    return Response(bio_mod.bio_payload(store, request=request))


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_bio_redirect(request, slug, key):
    """Redireciona um clique de link da página bio, contabilizando o clique. Nunca usa URL do request (anti open-redirect)."""
    from django.http import HttpResponseRedirect
    from apps.stores.models import BioClickStat
    from . import bio as bio_mod
    store = _get_active_store(slug)
    target = bio_mod.resolve_link_url(store, key)
    if not target:
        return HttpResponseRedirect(bio_mod.bio_page_url(store))
    BioClickStat.bump(store, key)
    return HttpResponseRedirect(target)


@cache_publico(60)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_catalog(request, slug):
    """Full catalog: store + categories with their products."""
    store = _get_active_store(slug)

    # Produtos ativos já com category + product_type (select_related) e variantes
    # ativas (prefetch filtrado) — colapsa o N+1 antigo (~1+2C+2P queries) p/ ~5 total.
    active_products = (
        StoreProduct.objects
        .filter(status='active')
        .select_related('category', 'product_type')
        .prefetch_related(Prefetch(
            'variants',
            queryset=StoreProductVariant.objects.filter(is_active=True).order_by('sort_order', 'name'),
        ))
        .order_by('sort_order', 'name')
    )
    categories = (
        StoreCategory.objects
        .filter(store=store, is_active=True)
        .prefetch_related(Prefetch('products', queryset=active_products))
        .order_by('sort_order', 'name')
    )

    catalog = []
    for cat in categories:
        products = list(cat.products.all())  # usa o cache do prefetch — zero query extra
        if not products:
            continue
        catalog.append({
            **PublicCategorySerializer(cat, context={'request': request}).data,
            'products': PublicProductSerializer(products, many=True, context={'request': request}).data,
        })

    return Response({
        'store': PublicStoreSerializer(store, context={'request': request}).data,
        'catalog': catalog,
    })


@cache_publico(60)
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


@cache_publico(60)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_products(request, slug):
    store = _get_active_store(slug)
    products = (
        StoreProduct.objects
        .filter(store=store, status='active')
        .select_related('category', 'product_type')
        .prefetch_related(Prefetch(
            'variants',
            queryset=StoreProductVariant.objects.filter(is_active=True).order_by('sort_order', 'name'),
        ))
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


@cache_publico(60)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_product_detail(request, slug, pk):
    store = _get_active_store(slug)
    product = get_object_or_404(StoreProduct, pk=pk, store=store, status='active')
    return Response(PublicProductSerializer(product, context={'request': request}).data)


@cache_publico(60)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_combos(request, slug):
    """Retorna todos os combos da loja com grupos e variantes."""
    store = _get_active_store(slug)
    combos = (
        StoreCombo.objects.filter(store=store, is_active=True)
        .prefetch_related('groups__product', 'groups__variant_limits__variant')
        .order_by('sort_order', 'name')
    )

    paginator = _PublicProductPagination()
    page = paginator.paginate_queryset(combos, request)
    serializer = PublicComboSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@nunca_cachear
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_store_availability(request, slug):
    """Return whether the store is currently open, plus today's hours."""
    store = _get_active_store(slug)
    # Dia LOCAL: `timezone.now()` é UTC, e das 21h à meia-noite em Brasília
    # `today` apontava para amanhã (o bot tinha o mesmo defeito, set16).
    now = timezone.localtime()
    day_name = now.strftime('%A').lower()
    hours = (store.operating_hours or {}).get(day_name)
    from apps.stores.services.agendamento import agenda, config_do_agendamento
    from apps.stores.services.horario_de_funcionamento import pausa_ativa
    pausa = pausa_ativa(store.metadata, timezone.now())
    return Response({
        'is_open': store.is_open(),
        # Só fim e motivo: o cardápio diz "volta às 14:00 — faltou gás".
        'pausa': {'fim': pausa.get('fim'), 'motivo': pausa.get('motivo') or ''} if pausa else None,
        'today': day_name,
        'hours': hours,
        'operating_hours': store.operating_hours or {},
        # Faixas de agendamento prontas: a vitrine só desenha (21/10).
        'agendamento': {
            'intervalo': config_do_agendamento(store)['intervalo'],
            # >0 = encomenda: a vitrine obriga a agendar e avisa no produto.
            'dias_de_antecedencia': config_do_agendamento(store)['dias_de_antecedencia'],
            'dias': agenda(store, now),
        },
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


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding self-service: cria dono + loja em trial
# ─────────────────────────────────────────────────────────────────────────────
class _PublicSignupThrottle(AnonRateThrottle):
    scope = 'auth'  # reusa o rate de auth (anti-abuso de signup)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([_PublicSignupThrottle])
def owner_signup(request):
    """
    POST /api/v1/public/signup/
    Cria o dono (User) + a Loja em trial (14d). Self-service onboarding.

    Body: { name, password, phone, email?, store_name, store_slug?, whatsapp? }
    Retorna: { token, user, store }  (201) ou erros de validação (400).
    """
    from datetime import timedelta
    from django.contrib.auth.models import User
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.utils.text import slugify
    from django.db import transaction
    from rest_framework.authtoken.models import Token
    from apps.core.models import UserProfile

    data = request.data
    name = (data.get('name') or '').strip()
    password = data.get('password') or ''
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip().lower()
    store_name = (data.get('store_name') or '').strip()
    store_slug = (data.get('store_slug') or '').strip()
    whatsapp = (data.get('whatsapp') or '').strip()

    errors = {}
    if not name:
        errors['name'] = ['Nome é obrigatório']
    if not store_name:
        errors['store_name'] = ['Nome da loja é obrigatório']
    if not phone and not email:
        errors['phone'] = ['Email ou celular é obrigatório']
    try:
        validate_password(password)
    except DjangoValidationError as e:
        errors['password'] = list(e.messages)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    if not email and phone:
        email = f"{phone.replace('+', '').replace('-', '').replace(' ', '')}@cardapidex.local"

    if User.objects.filter(email__iexact=email).exists():
        return Response({'email': ['Este e-mail já está cadastrado']}, status=status.HTTP_400_BAD_REQUEST)
    if phone and UserProfile.objects.filter(phone=phone).exists():
        return Response({'phone': ['Este celular já está cadastrado']}, status=status.HTTP_400_BAD_REQUEST)

    base_slug = slugify(store_slug or store_name)[:90] or 'loja'
    slug = base_slug
    i = 1
    while Store.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{i}"
        i += 1

    parts = name.split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''

    base_username = (email.split('@')[0] or 'dono')[:20]
    username = base_username
    c = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{c}"
        c += 1

    with transaction.atomic():
        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
        )
        if phone:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save()
        store = Store.objects.create(
            name=store_name, slug=slug, owner=user,
            status=Store.StoreStatus.ACTIVE,
            plan=Store.StorePlan.STARTER,
            trial_ends_at=timezone.now() + timedelta(days=14),
            onboarding_completed=False,
            whatsapp_number=whatsapp or '',
        )
        from apps.stores.models import StoreSubscription
        StoreSubscription.objects.create(
            store=store,
            plan=store.plan,
            status=StoreSubscription.Status.TRIALING,
        )
        token = Token.objects.create(user=user)

    return Response({
        'token': token.key,
        'user': {'id': user.id, 'email': user.email, 'name': name},
        'store': {
            'id': str(store.id), 'slug': store.slug, 'name': store.name,
            'trial_ends_at': store.trial_ends_at.isoformat(),
            'onboarding_completed': store.onboarding_completed,
        },
    }, status=status.HTTP_201_CREATED)


def _lojas_do_marketplace():
    """(loja, logo) das lojas que aparecem no app: ativa, com cidade, logo e
    produto ativo, sem `metadata.fora_do_marketplace`. Fonte única da vitrine
    e dos benefícios — as duas telas não podem discordar de quem está no app."""
    from django.db.models import Avg, Count, Q

    lojas = (
        Store.objects.filter(status='active')
        .exclude(city='')
        .annotate(
            total_produtos=Count('products', filter=Q(
                products__is_active=True,
                products__status=StoreProduct.ProductStatus.ACTIVE), distinct=True),
            nota=Avg('reviews__rating', filter=Q(reviews__is_public=True)),
            total_avaliacoes=Count('reviews', filter=Q(reviews__is_public=True), distinct=True),
        )
        .filter(total_produtos__gt=0)
    )
    for s in lojas:
        # Filtro em Python: `exclude(metadata__chave=True)` no JSON também
        # descarta a loja que nem tem a chave (NOT NULL vira NULL no SQL).
        if (s.metadata or {}).get('fora_do_marketplace') is True:
            continue
        logo = s.get_logo_url()
        if logo:
            yield s, logo


@cache_publico(300)
@cache_publico(60)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_marketplace(request):
    """GET /api/v1/public/marketplace/ — vitrine de lojas do app Cardapidex.

    Entra loja ativa e pronta para vender: com logo, cidade e produto ativo.
    `metadata.fora_do_marketplace` tira a loja da vitrine sem desativá-la.
    Abertas primeiro; dentro de cada grupo, as com mais produtos.
    """
    from apps.stores.services.delivery_quote_service import DeliveryQuoteService

    itens = []
    for s, logo in _lojas_do_marketplace():
        itens.append({
            'slug': s.slug,
            'nome': s.name,
            'descricao': s.tagline or '',
            'logo_url': logo,
            'capa_url': s.get_banner_url() or '',
            'cor': s.primary_color or '',
            'cidade': s.city,
            'estado': s.state,
            'tipo': s.store_type,
            'aberta': bool(s.is_open()),
            'entrega': bool(s.delivery_enabled),
            'retirada': bool(s.pickup_enabled),
            'frete': str(DeliveryQuoteService.taxa_base(s)),
            'frete_gratis_a_partir': str(s.free_delivery_threshold) if s.free_delivery_threshold else None,
            'pedido_minimo': str(s.min_order_value),
            'prazo_min': s.prazo_entrega_min,
            'prazo_max': s.prazo_entrega_max,
            'nota': round(float(s.nota), 1) if s.nota is not None else None,
            'total_avaliacoes': s.total_avaliacoes,
            'total_produtos': s.total_produtos,
        })
    itens.sort(key=lambda i: (not i['aberta'], -i['total_produtos'], i['nome']))
    return Response({'lojas': itens})



@nunca_cachear
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_marketplace_beneficios(request):
    """GET /api/v1/public/marketplace/beneficios/ — vantagens de cada loja do app.

    O perfil do app é do marketplace: mostra, loja por loja, o cupom em
    destaque (o mesmo do banner do cardápio), o cashback e a fidelidade. Logado,
    vem o progresso e o saldo da própria pessoa, e o cupom de primeira compra
    some onde ela já comprou (mesma regra do banner, 28/10). Por pessoa, então
    nunca cacheado.
    """
    from apps.stores import billing
    from apps.stores.api.views.loyalty_views import _user_phone, resolve_loyalty_status_for_user
    from apps.stores.models import StoreCoupon
    from apps.stores.services.cashback_service import CashbackService
    from apps.stores.services.loyalty_service import LoyaltyService

    user = request.user if request.user.is_authenticated else None
    phone = _user_phone(user) if user else ''
    itens = []
    for s, logo in _lojas_do_marketplace():
        cupons = []
        if billing.plan_allows(s, 'coupon_banner'):
            for c in StoreCoupon.objects.filter(store=s, is_active=True, is_featured=True).order_by('-created_at'):
                ok, _ = c.is_valid(user=user, customer_phone=phone or None)
                if not ok:
                    continue
                cupons.append({
                    'code': c.code,
                    'description': c.description,
                    'discount_type': c.discount_type,
                    'discount_value': str(c.discount_value),
                    'min_purchase': str(c.min_purchase),
                    'first_order_only': c.first_order_only,
                    'valid_until': c.valid_until.isoformat(),
                })

        fidelidade = None
        threshold, ligada = LoyaltyService._config(s)
        if ligada:
            _, plural = LoyaltyService.item_labels(s)
            status = resolve_loyalty_status_for_user(s, user) if user else {}
            fidelidade = {
                'threshold': threshold,
                'item_label_plural': plural,
                'progresso': int(status.get('progress') or 0),
                'premios': int(status.get('available_rewards') or 0),
            }

        cashback = None
        if CashbackService.is_enabled(s):
            saldo = CashbackService.balance(s, phone, True) if phone else Decimal('0.00')
            vence = CashbackService.expires_next(s, phone, True) if phone else None
            cashback = {
                'percent': float(CashbackService.percent(s)),
                'saldo': str(saldo),
                'vence': vence.isoformat() if vence else None,
            }

        itens.append({
            'slug': s.slug,
            'nome': s.name,
            'logo_url': logo,
            'cor': s.primary_color or '',
            'cupons': cupons,
            'fidelidade': fidelidade,
            'cashback': cashback,
        })
    return Response({'lojas': itens})

@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([_PublicReadThrottle])
def public_plans(request):
    """GET /api/v1/public/plans/ — catálogo de planos SaaS (landing/dash)."""
    from apps.stores.billing import public_adicionais, public_catalog
    return Response({'plans': public_catalog(), 'adicionais': public_adicionais()})
