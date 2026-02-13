"""
Product management API views.
"""
import uuid as uuid_module
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from apps.stores.models import (
    StoreCategory, StoreProduct, StoreProductVariant, 
    StoreCombo, StoreProductType
)
from ..serializers import (
    StoreCategorySerializer,
    StoreProductSerializer, StoreProductCreateSerializer,
    StoreProductVariantSerializer,
    StoreComboSerializer, StoreProductTypeSerializer
)
from .base import IsStoreOwnerOrStaff, filter_by_store


class StoreCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store categories."""
    
    serializer_class = StoreCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreCategory.objects.all()
        queryset, filtered = filter_by_store(queryset, store_param)
        if filtered:
            return queryset.order_by('sort_order', 'name')
        
        user = self.request.user
        if user.is_staff:
            return queryset.order_by('sort_order', 'name')
        return queryset.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct().order_by('sort_order', 'name')


class StoreProductViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store products."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreProduct.objects.all()
        
        queryset, filtered = filter_by_store(queryset, store_param)
        if not filtered:
            user = self.request.user
            if not user.is_staff:
                queryset = queryset.filter(
                    Q(store__owner=user) | Q(store__staff=user)
                ).distinct()
        
        # Filters
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        featured = self.request.query_params.get('featured')
        if featured:
            queryset = queryset.filter(featured=featured.lower() == 'true')
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset.select_related('category', 'store')
    
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
        if product_id:
            return StoreProductVariant.objects.filter(product_id=product_id)
        return StoreProductVariant.objects.none()


class StoreComboViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store combos."""
    
    serializer_class = StoreComboSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        import uuid as uuid_module
        store_param = self.request.query_params.get('store')
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
        
        if self.action == 'list' and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('store').prefetch_related('items__product')


class StoreProductTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for managing product types."""
    
    serializer_class = StoreProductTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
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
        
        if self.action == 'list' and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('store').order_by('sort_order', 'name')


class StoreProductTypeAdminViewSet(viewsets.ModelViewSet):
    """Admin ViewSet for managing product types."""
    
    serializer_class = StoreProductTypeSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        import uuid as uuid_module
        store_param = self.request.query_params.get('store')
        queryset = StoreProductType.objects.all()
        
        if store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        user = self.request.user
        if not user.is_staff:
            from apps.stores.models import Store
            user_stores = Store.objects.filter(
                Q(owner=user) | Q(staff=user)
            ).values_list('id', flat=True)
            queryset = queryset.filter(store_id__in=user_stores)
        
        return queryset.select_related('store').order_by('sort_order', 'name')
