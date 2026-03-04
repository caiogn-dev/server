"""
Commerce - URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StoreViewSet, CategoryViewSet, ProductViewSet, CustomerViewSet, OrderViewSet
from .reports_views import (
    DashboardStatsView, RevenueReportView, ProductsReportView,
    StockReportView, CustomersReportView, OrdersExportView
)

router = DefaultRouter()
router.register(r'stores', StoreViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'orders', OrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
    
    # Store-specific orders endpoint
    path('<slug:store_slug>/orders/', OrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='store-orders'),
    path('<slug:store_slug>/orders/<str:pk>/', OrderViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='store-order-detail'),
    
    # Reports & Analytics
    path('reports/dashboard/', DashboardStatsView.as_view(), name='commerce-dashboard-stats'),
    path('reports/revenue/', RevenueReportView.as_view(), name='commerce-revenue-report'),
    path('reports/products/', ProductsReportView.as_view(), name='commerce-products-report'),
    path('reports/stock/', StockReportView.as_view(), name='commerce-stock-report'),
    path('reports/customers/', CustomersReportView.as_view(), name='commerce-customers-report'),
    path('reports/orders/export/', OrdersExportView.as_view(), name='commerce-orders-export'),
]
