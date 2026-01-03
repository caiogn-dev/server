from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'cart', views.CartViewSet, basename='cart')
router.register(r'checkout', views.CheckoutViewSet, basename='checkout')
router.register(r'webhooks', views.WebhookViewSet, basename='webhook')

urlpatterns = [
    path('', include(router.urls)),
]
