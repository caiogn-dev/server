"""
URL patterns for the Pastita Panel.
Served at /panel/
"""
from django.urls import path
from . import views

app_name = 'panel'

urlpatterns = [
    # Auth
    path('login/',  views.panel_login,  name='login'),
    path('logout/', views.panel_logout, name='logout'),

    # Store selector (multi-tenant entry point)
    path('stores/', views.store_select, name='stores'),

    # Dashboard (root of the panel — requires store selected)
    path('',        views.dashboard,    name='dashboard'),

    # Orders
    path('orders/',                        views.orders_list,  name='orders'),
    path('orders/<uuid:order_id>/',        views.order_detail, name='order_detail'),

    # Conversations
    path('conversations/', views.conversations_list, name='conversations'),

    # Products
    path('products/', views.products_list, name='products'),

    # Customers
    path('customers/', views.customers_list, name='customers'),

    # Settings
    path('settings/', views.store_settings, name='settings'),

    # AJAX
    path('api/switch-store/', views.api_switch_store, name='api_switch_store'),
]
