"""
Public API URL patterns.
All endpoints use AllowAny — safe for public storefront access.
"""
from django.urls import path
from . import views

app_name = 'public_api'

urlpatterns = [
    path('<slug:slug>/', views.public_store_detail, name='store-detail'),
    path('<slug:slug>/catalog/', views.public_store_catalog, name='store-catalog'),
    path('<slug:slug>/categories/', views.public_store_categories, name='store-categories'),
    path('<slug:slug>/products/', views.public_store_products, name='store-products'),
    path('<slug:slug>/products/<uuid:pk>/', views.public_product_detail, name='product-detail'),
    path('<slug:slug>/availability/', views.public_store_availability, name='store-availability'),
]
