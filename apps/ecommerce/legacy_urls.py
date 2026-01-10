"""
Legacy e-commerce URLs for backward compatibility.

These URLs are mounted at /api/v1/ (without /ecommerce/ prefix) to support
the pastita-3d frontend which uses:
- /api/v1/products/
- /api/v1/cart/
- /api/v1/checkout/
- /api/v1/orders/history/
- /api/v1/coupons/
- /api/v1/delivery/
- /api/v1/wishlist/

The new URLs at /api/v1/ecommerce/ are used by pastita-dash admin panel.

DO NOT REMOVE - Required for pastita-3d frontend compatibility.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import (
    ProductViewSet, CartViewSet, CheckoutViewSet, OrdersHistoryView,
    WishlistViewSet, CouponViewSet, DeliveryViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='legacy-product')
router.register(r'cart', CartViewSet, basename='legacy-cart')
router.register(r'checkout', CheckoutViewSet, basename='legacy-checkout')
router.register(r'wishlist', WishlistViewSet, basename='legacy-wishlist')
router.register(r'coupons', CouponViewSet, basename='legacy-coupon')
router.register(r'delivery', DeliveryViewSet, basename='legacy-delivery')

urlpatterns = [
    path('', include(router.urls)),
    path('orders/history/', OrdersHistoryView.as_view(), name='legacy-orders-history'),
]
