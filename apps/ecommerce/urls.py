"""
E-commerce app URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    ProductViewSet, CartViewSet, CheckoutViewSet, WebhookViewSet, 
    OrdersHistoryView, WishlistViewSet, CouponViewSet, DeliveryViewSet,
    CouponAdminViewSet, DeliveryZoneAdminViewSet, StoreLocationAdminViewSet,
    ProductAdminViewSet, GeocodingViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'checkout', CheckoutViewSet, basename='checkout')
router.register(r'webhooks', WebhookViewSet, basename='ecommerce-webhook')
router.register(r'wishlist', WishlistViewSet, basename='wishlist')
router.register(r'coupons', CouponViewSet, basename='coupon')
router.register(r'delivery', DeliveryViewSet, basename='delivery')
router.register(r'geocoding', GeocodingViewSet, basename='geocoding')

# Admin routes
router.register(r'admin/coupons', CouponAdminViewSet, basename='admin-coupon')
router.register(r'admin/delivery-zones', DeliveryZoneAdminViewSet, basename='admin-delivery-zone')
router.register(r'admin/store-location', StoreLocationAdminViewSet, basename='admin-store-location')
router.register(r'admin/products', ProductAdminViewSet, basename='admin-product')

urlpatterns = [
    path('', include(router.urls)),
    path('orders/history/', OrdersHistoryView.as_view(), name='orders-history'),
]
