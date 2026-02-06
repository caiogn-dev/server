"""
Storefront API views for public store access.

These views handle cart, checkout, catalog, and wishlist functionality
for the public-facing storefront.
"""
import logging
from decimal import Decimal
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

from apps.stores.models import (
    Store, StoreProduct, StoreCategory, StoreCart, StoreCartItem,
    StoreCombo, StoreProductType, StoreCoupon, StoreDeliveryZone,
    StoreWishlist
)
from apps.stores.services import cart_service, checkout_service, here_maps_service
from ..serializers import (
    StoreSerializer, StoreCategorySerializer, StoreProductSerializer,
    StoreCartSerializer, StoreCartItemSerializer, StoreComboSerializer,
    StoreProductTypeSerializer, StoreWishlistSerializer, WishlistAddRemoveSerializer
)

logger = logging.getLogger(__name__)


class StorePublicView(APIView):
    """Public store information endpoint."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """Get public store information."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        serializer = StoreSerializer(store)
        return Response(serializer.data)


class StoreCatalogView(APIView):
    """Public catalog endpoint for a store."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """Get store catalog with categories, products, and combos."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        # Get all active products for the store
        products = StoreProduct.objects.filter(
            store=store, status='active'
        ).order_by('sort_order', 'name')
        
        # Get featured products
        featured_products = products.filter(featured=True)
        
        # Get active categories with their products
        categories = StoreCategory.objects.filter(
            store=store, is_active=True
        ).prefetch_related(
            Prefetch(
                'products',
                queryset=StoreProduct.objects.filter(status='active').order_by('sort_order', 'name')
            )
        ).order_by('sort_order', 'name')
        
        # Build products_by_category
        products_by_category = []
        for category in categories:
            category_products = products.filter(category=category)
            if category_products.exists():
                products_by_category.append({
                    'category': StoreCategorySerializer(category).data,
                    'products': StoreProductSerializer(category_products, many=True).data
                })
        
        # Get combos
        combos = StoreCombo.objects.filter(
            store=store, is_active=True
        ).prefetch_related('items__product').order_by('sort_order', 'name')
        
        # Get featured combos (combos_destaque)
        combos_destaque = combos.filter(featured=True)
        
        # Get product types
        product_types = StoreProductType.objects.filter(
            store=store, is_active=True
        ).order_by('sort_order', 'name')
        
        return Response({
            'store': StoreSerializer(store).data,
            'categories': StoreCategorySerializer(categories, many=True).data,
            'products': StoreProductSerializer(products, many=True).data,
            'featured_products': StoreProductSerializer(featured_products, many=True).data,
            'combos': StoreComboSerializer(combos, many=True).data,
            'combos_destaque': StoreComboSerializer(combos_destaque, many=True).data,
            'product_types': StoreProductTypeSerializer(product_types, many=True).data,
            'products_by_category': products_by_category,
        })


class StoreCartViewSet(viewsets.ViewSet):
    """ViewSet for managing shopping carts."""
    permission_classes = [permissions.AllowAny]
    
    def get_store(self, store_slug):
        return get_object_or_404(Store, slug=store_slug, status='active')
    
    def get_cart(self, request, store):
        """Get or create cart for session/user."""
        session_id = request.session.session_key
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        
        user = request.user if request.user.is_authenticated else None
        return cart_service.get_or_create_cart(store, user, session_id)
    
    def get_cart_by_store(self, request, store_slug=None):
        """Get cart for a specific store."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        serializer = StoreCartSerializer(cart)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def add_item(self, request, store_slug=None):
        """Add item to cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        variant_id = request.data.get('variant_id')
        notes = request.data.get('notes', '')
        
        if not product_id:
            return Response(
                {'error': 'product_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            cart_item = cart_service.add_item(
                cart, product_id, quantity, variant_id, notes
            )
            return Response(StoreCartSerializer(cart).data)
        except Exception as e:
            logger.error(f"Error adding item to cart: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['patch'], url_path='item/(?P<item_id>[^/.]+)')
    def update_item(self, request, store_slug=None, item_id=None):
        """Update cart item quantity."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        quantity = request.data.get('quantity')
        if quantity is not None:
            quantity = int(quantity)
            if quantity <= 0:
                cart_service.remove_item(cart, item_id)
            else:
                cart_service.update_item_quantity(cart, item_id, quantity)
        
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['delete'], url_path='item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, store_slug=None, item_id=None):
        """Remove item from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.remove_item(cart, item_id)
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['delete'])
    def clear_cart(self, request, store_slug=None):
        """Clear all items from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.clear_cart(cart)
        return Response(StoreCartSerializer(cart).data)


class StoreCheckoutView(APIView):
    """Checkout endpoint for creating orders."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, store_slug):
        """Process checkout and create order."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        # Get cart
        session_id = request.session.session_key
        user = request.user if request.user.is_authenticated else None
        cart = cart_service.get_or_create_cart(store, user, session_id)
        
        if not cart.items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract checkout data
        checkout_data = {
            'customer_name': request.data.get('customer_name'),
            'customer_email': request.data.get('customer_email'),
            'customer_phone': request.data.get('customer_phone'),
            'delivery_type': request.data.get('delivery_type', 'delivery'),
            'delivery_address': request.data.get('delivery_address'),
            'delivery_lat': request.data.get('delivery_lat'),
            'delivery_lng': request.data.get('delivery_lng'),
            'payment_method': request.data.get('payment_method'),
            'coupon_code': request.data.get('coupon_code'),
            'notes': request.data.get('notes', ''),
        }
        
        try:
            order = checkout_service.create_order(cart, checkout_data)
            return Response({
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': str(order.total),
                'payment_status': order.payment_status,
                'access_token': order.access_token,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreDeliveryFeeView(APIView):
    """Calculate delivery fee endpoint."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, store_slug):
        """Calculate delivery fee for an address."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        address = request.data.get('address')
        
        if not (lat and lng) and not address:
            return Response(
                {'error': 'Either lat/lng or address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # If only address provided, geocode it
            if not (lat and lng) and address:
                geocode_result = here_maps_service.geocode(address)
                if geocode_result:
                    lat = geocode_result.get('lat')
                    lng = geocode_result.get('lng')
                else:
                    return Response(
                        {'error': 'Could not geocode address'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Calculate delivery fee
            delivery_info = here_maps_service.calculate_delivery_fee(
                store, float(lat), float(lng)
            )
            return Response(delivery_info)
        except Exception as e:
            logger.error(f"Delivery fee calculation error: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class StoreCouponValidateView(APIView):
    """Validate coupon code endpoint."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, store_slug):
        """Validate a coupon code."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        code = request.data.get('code')
        subtotal = Decimal(str(request.data.get('subtotal', 0)))
        
        if not code:
            return Response(
                {'error': 'Coupon code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            coupon = StoreCoupon.objects.get(
                store=store,
                code__iexact=code,
                is_active=True
            )
            
            # Check validity
            if not coupon.is_valid():
                return Response({
                    'valid': False,
                    'error': 'Coupon is expired or no longer valid'
                })
            
            # Check minimum order
            if coupon.minimum_order and subtotal < coupon.minimum_order:
                return Response({
                    'valid': False,
                    'error': f'Minimum order of {coupon.minimum_order} required'
                })
            
            # Calculate discount
            if coupon.discount_type == 'percentage':
                discount = subtotal * (coupon.discount_value / 100)
                if coupon.maximum_discount:
                    discount = min(discount, coupon.maximum_discount)
            else:
                discount = coupon.discount_value
            
            return Response({
                'valid': True,
                'coupon': {
                    'code': coupon.code,
                    'discount_type': coupon.discount_type,
                    'discount_value': str(coupon.discount_value),
                    'calculated_discount': str(discount),
                }
            })
        except StoreCoupon.DoesNotExist:
            return Response({
                'valid': False,
                'error': 'Invalid coupon code'
            })


class StoreWishlistViewSet(viewsets.ViewSet):
    """ViewSet for managing user wishlists per store."""
    permission_classes = [permissions.AllowAny]
    
    def get_store(self, store_slug):
        return get_object_or_404(Store, slug=store_slug, status='active')
    
    def _get_customer_id(self, request):
        """Get customer identifier from request."""
        if request.user.is_authenticated:
            return {'customer_email': request.user.email}
        # Try to get from session or request data
        phone = request.data.get('customer_phone') or request.session.get('customer_phone')
        email = request.data.get('customer_email') or request.session.get('customer_email')
        if phone:
            return {'customer_phone': phone}
        if email:
            return {'customer_email': email}
        return None
    
    def list(self, request, store_slug=None):
        """Get user's wishlist for a store."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response({
                'products': [],
                'count': 0
            })
        
        wishlist_items = StoreWishlist.objects.filter(store=store, **customer_id)
        products = [item.product for item in wishlist_items]
        
        return Response({
            'products': StoreProductSerializer(products, many=True).data,
            'count': len(products)
        })
    
    @action(detail=False, methods=['post'])
    def add(self, request, store_slug=None):
        """Add a product to the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist_item, created = StoreWishlist.objects.get_or_create(
            store=store,
            product=product,
            **customer_id
        )
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product added to wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist_count
        })
    
    @action(detail=False, methods=['post'])
    def remove(self, request, store_slug=None):
        """Remove a product from the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        
        StoreWishlist.objects.filter(
            store=store,
            product_id=product_id,
            **customer_id
        ).delete()
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product removed from wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist_count
        })
    
    @action(detail=False, methods=['post'])
    def toggle(self, request, store_slug=None):
        """Toggle a product in the wishlist."""
        store = self.get_store(store_slug)
        customer_id = self._get_customer_id(request)
        
        if not customer_id:
            return Response(
                {'error': 'Authentication required or customer_phone/email needed'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist_item = StoreWishlist.objects.filter(
            store=store,
            product=product,
            **customer_id
        ).first()
        
        if wishlist_item:
            wishlist_item.delete()
            added = False
        else:
            StoreWishlist.objects.create(
                store=store,
                product=product,
                **customer_id
            )
            added = True
        
        wishlist_count = StoreWishlist.objects.filter(store=store, **customer_id).count()
        
        return Response({
            'message': 'Product added to wishlist' if added else 'Product removed from wishlist',
            'product_id': str(product_id),
            'in_wishlist': added,
            'wishlist_count': wishlist_count
        })
