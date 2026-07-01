"""
Product management API views.
"""
import uuid as uuid_module
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import Q

from apps.stores.models import (
    StoreCategory, StoreProduct, StoreProductVariant,
    StoreCombo, StoreProductType
)
from apps.core.permissions import StoreQuerysetMixin
from ..serializers import (
    StoreCategorySerializer,
    StoreProductSerializer, StoreProductCreateSerializer,
    StoreProductVariantSerializer,
    StoreComboSerializer, StoreProductTypeSerializer
)
from .base import IsStoreOwnerOrStaff, filter_by_store


class StoreCatalogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 500


class StoreCategoryViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing store categories."""

    queryset = StoreCategory.objects.all()
    serializer_class = StoreCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def initialize_request(self, request, *args, **kwargs):
        """Override to resolve store slug to UUID if needed."""
        store_pk = self.kwargs.get('store_pk')
        if store_pk:
            try:
                uuid_module.UUID(str(store_pk))
            except (ValueError, AttributeError):
                from apps.stores.models import Store
                try:
                    store = Store.objects.get(slug=store_pk)
                    self.kwargs['store_pk'] = str(store.id)
                except Store.DoesNotExist:
                    pass
        return super().initialize_request(request, *args, **kwargs)

    def get_queryset(self):
        from django.db.models import Count, Q, Prefetch
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if store_param:
            qs, _ = filter_by_store(qs, store_param)
        # products_count vinha de products.count() POR categoria e get_children de
        # children.filter() POR categoria → N+1. Annotate conta os produtos ativos no
        # JOIN (1 query) e o Prefetch dos filhos ativos (já anotados) elimina a query
        # por linha. O serializer lê a annotation/o cache do prefetch.
        active_products = Count('products', filter=Q(products__status='active'))
        children_qs = qs.model.objects.filter(is_active=True).annotate(
            anno_products_count=active_products,
        ).order_by('sort_order', 'name')
        return qs.annotate(
            anno_products_count=active_products,
        ).prefetch_related(
            Prefetch('children', queryset=children_qs),
        ).order_by('sort_order', 'name')


class StoreProductViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing store products."""

    queryset = StoreProduct.objects.all()
    pagination_class = StoreCatalogPagination
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def initialize_request(self, request, *args, **kwargs):
        """Override to resolve store slug to UUID if needed."""
        store_pk = self.kwargs.get('store_pk')
        if store_pk:
            try:
                uuid_module.UUID(str(store_pk))
            except (ValueError, AttributeError):
                # It's a slug, resolve to UUID
                from apps.stores.models import Store
                try:
                    store = Store.objects.get(slug=store_pk)
                    self.kwargs['store_pk'] = str(store.id)
                except Store.DoesNotExist:
                    pass
        return super().initialize_request(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        if store_param:
            qs, _ = filter_by_store(qs, store_param)

        # Filters
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_id=category)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        featured = self.request.query_params.get('featured')
        if featured:
            qs = qs.filter(featured=featured.lower() == 'true')

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(description__icontains=search)
            )

        # Optimize based on action (list vs. detail)
        if self.action in ['retrieve']:
            # Detail view: full related data
            qs = qs.select_related(
                'category',
                'store',
            ).prefetch_related(
                'variants',
                'options',
                'combos',
            )
        else:
            # List view: o serializer SEMPRE serializa `variants` (reverse FK) e lê
            # `product_type` (FK) por linha → sem isto era 1 query de variants por
            # produto (N+1, até ~500 no page_size cheio). prefetch/select_related
            # tornam O(1). images é JSONField (não é relação).
            qs = qs.select_related(
                'category',
                'store',
                'product_type',
            ).prefetch_related(
                'variants',
            )

        return qs
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreProductCreateSerializer
        return StoreProductSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Toggle product active/inactive status."""
        product = self.get_object()
        if product.status == 'active':
            product.status = 'inactive'
        else:
            product.status = 'active'
        product.save(update_fields=['status', 'updated_at'])
        return Response({'status': product.status})
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pausa rápida do produto. Body: {minutes: int} ou vazio = até amanhã."""
        from datetime import timedelta
        from django.utils import timezone

        product = self.get_object()
        minutes = request.data.get('minutes')
        if minutes:
            product.paused_until = timezone.now() + timedelta(minutes=int(minutes))
        else:
            # Até amanhã: meia-noite local do dia seguinte
            tomorrow = timezone.localtime() + timedelta(days=1)
            product.paused_until = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        product.save(update_fields=['paused_until', 'updated_at'])
        return Response({
            'is_paused': product.is_paused,
            'paused_until': product.paused_until,
        })

    @action(detail=True, methods=['post'])
    def unpause(self, request, pk=None):
        """Remove a pausa do produto."""
        product = self.get_object()
        product.paused_until = None
        product.save(update_fields=['paused_until', 'updated_at'])
        return Response({'is_paused': False, 'paused_until': None})

    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle product featured status."""
        product = self.get_object()
        product.featured = not product.featured
        product.save(update_fields=['featured', 'updated_at'])
        return Response({'featured': product.featured})
    
    @action(detail=True, methods=['post'])
    def update_stock(self, request, pk=None):
        """Update product stock quantity."""
        from rest_framework import status
        product = self.get_object()
        quantity = request.data.get('quantity')
        if quantity is None:
            return Response(
                {'error': 'quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        product.stock_quantity = int(quantity)
        product.save(update_fields=['stock_quantity', 'updated_at'])
        return Response({'stock_quantity': product.stock_quantity})
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a product."""
        product = self.get_object()
        
        new_product = StoreProduct.objects.create(
            store=product.store,
            category=product.category,
            name=f"{product.name} (Copy)",
            slug=f"{product.slug}-copy",
            description=product.description,
            short_description=product.short_description,
            price=product.price,
            compare_at_price=product.compare_at_price,
            cost_price=product.cost_price,
            track_stock=product.track_stock,
            stock_quantity=0,
            low_stock_threshold=product.low_stock_threshold,
            status='inactive',
            attributes=product.attributes,
            tags=product.tags
        )
        
        return Response(StoreProductSerializer(new_product).data)


class StoreProductVariantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing product variants."""
    
    serializer_class = StoreProductVariantSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_pk')
        if not product_id:
            return StoreProductVariant.objects.none()
        qs = StoreProductVariant.objects.filter(product_id=product_id)
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            from apps.core.permissions import accessible_store_ids
            qs = qs.filter(product__store__id__in=accessible_store_ids(user))
        return qs


COMBO_PREFETCH = (
    'groups__product',
    'groups__variant_limits__variant__product',
    'groups__product_options__product',
)


class StoreComboViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store combos."""

    serializer_class = StoreComboSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    # Mesmo paginador do catálogo: suporta ?page_size= (o painel pagina a
    # listagem de combos). Sem isso o page_size do request era ignorado.
    pagination_class = StoreCatalogPagination

    @classmethod
    def queryset_for_test(cls, store):
        """Queryset filtrado por loja com o mesmo prefetch do get_queryset."""
        return StoreCombo.objects.filter(store=store).prefetch_related(*COMBO_PREFETCH)

    def _assert_store_access(self, store):
        from rest_framework.exceptions import PermissionDenied
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied("Autenticação necessária.")
        if user.is_staff or user.is_superuser:
            return
        perm = IsStoreOwnerOrStaff()
        if not perm._user_can_access_store(user, store):
            raise PermissionDenied("Você não tem acesso a esta loja.")

    def perform_create(self, serializer):
        store = serializer.validated_data.get('store')
        if store:
            self._assert_store_access(store)
            # Feature-gate: limite de produtos por plano (lojas exempt/grandfather passam).
            from apps.stores import billing
            from rest_framework.exceptions import ValidationError as DRFValidationError
            if not billing.within_product_limit(store, store.products.count()):
                cap = billing.plan_limits(getattr(store, 'plan', billing.DEFAULT_PLAN)).get('max_products')
                raise DRFValidationError({
                    'detail': f'Limite do plano atingido ({cap} produtos). '
                              f'Faça upgrade do plano para adicionar mais.'
                })
        serializer.save()

    def perform_update(self, serializer):
        store = serializer.instance.store
        self._assert_store_access(store)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_store_access(instance.store)
        instance.delete()

    def get_queryset(self):
        import uuid as uuid_module
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        store_slug = self.kwargs.get('store_slug')

        queryset = StoreCombo.objects.all()

        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        elif store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        else:
            # Sem escopo de loja explícito na URL ou nos query params:
            # restringir por tenant para evitar IDOR cross-tenant.
            # Superuser mantém visão global; anônimo recebe queryset vazio.
            user = self.request.user
            if not user.is_authenticated:
                queryset = queryset.none()
            elif not user.is_superuser:
                from apps.core.permissions import accessible_store_ids
                queryset = queryset.filter(store_id__in=accessible_store_ids(user))

        # Only hide inactive combos for unauthenticated / non-staff public requests
        is_admin = self.request.user.is_authenticated and (
            self.request.user.is_staff or self.request.user.is_superuser
        )
        if self.action == 'list' and not is_admin:
            queryset = queryset.filter(is_active=True)

        # Filtro explícito ?is_active=true|false (usado pelo painel). Só admins
        # conseguem pedir os inativos; para os demais o filtro acima já restringe.
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            wants_active = is_active_param.lower() in ('1', 'true', 'yes')
            queryset = queryset.filter(is_active=wants_active)

        return queryset.select_related('store').prefetch_related(*COMBO_PREFETCH)


class StoreProductTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for managing product types."""

    serializer_class = StoreProductTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def _assert_store_access(self, store):
        from rest_framework.exceptions import PermissionDenied
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied("Autenticação necessária.")
        if user.is_staff or user.is_superuser:
            return
        perm = IsStoreOwnerOrStaff()
        if not perm._user_can_access_store(user, store):
            raise PermissionDenied("Você não tem acesso a esta loja.")

    def perform_create(self, serializer):
        store = serializer.validated_data.get('store')
        if store:
            self._assert_store_access(store)
        serializer.save()

    def perform_update(self, serializer):
        self._assert_store_access(serializer.instance.store)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_store_access(instance.store)
        instance.delete()

    def get_queryset(self):
        import uuid as uuid_module
        store_param = self.request.query_params.get('store')
        store_slug = self.kwargs.get('store_slug')

        queryset = StoreProductType.objects.all()

        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        elif store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        else:
            # Sem escopo de loja explícito: restringir por tenant (IDOR fix).
            user = self.request.user
            if not user.is_authenticated:
                queryset = queryset.none()
            elif not user.is_superuser:
                from apps.core.permissions import accessible_store_ids
                queryset = queryset.filter(store_id__in=accessible_store_ids(user))

        if self.action == 'list' and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)

        return queryset.select_related('store').order_by('sort_order', 'name')


class StoreProductTypeAdminViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """Admin ViewSet for managing product types."""

    queryset = StoreProductType.objects.all()
    serializer_class = StoreProductTypeSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        store_param = self.request.query_params.get('store')
        if store_param:
            qs, _ = filter_by_store(qs, store_param)
        return qs.select_related('store').order_by('sort_order', 'name')
