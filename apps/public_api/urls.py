"""
Public API URL patterns.
All endpoints use AllowAny — safe for public storefront access.
"""
from django.urls import path
from . import views

app_name = 'public_api'

urlpatterns = [
    path('leads/', views.create_lead, name='create-lead'),
    path('signup/', views.owner_signup, name='owner-signup'),
    path('plans/', views.public_plans, name='public-plans'),
    path('store-by-domain/', views.store_by_domain, name='store-by-domain'),
    path('<slug:slug>/', views.public_store_detail, name='store-detail'),
    path('<slug:slug>/bio/r/<str:key>/', views.public_store_bio_redirect, name='public-store-bio-redirect'),
    path('<slug:slug>/bio/', views.public_store_bio, name='public-store-bio'),
    path('<slug:slug>/catalog/', views.public_store_catalog, name='store-catalog'),
    path('<slug:slug>/categories/', views.public_store_categories, name='store-categories'),
    path('<slug:slug>/products/', views.public_store_products, name='store-products'),
    path('<slug:slug>/products/<uuid:pk>/', views.public_product_detail, name='product-detail'),
    path('<slug:slug>/combos/', views.public_store_combos, name='store-combos'),
    path('<slug:slug>/availability/', views.public_store_availability, name='store-availability'),
]
