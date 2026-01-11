"""
Pastita URLs - REST API routes for the Pastita app.
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

from . import api_views

app_name = 'pastita'

# Create router for ViewSets
router = DefaultRouter()
router.register(r'produtos', api_views.ProdutoViewSet, basename='produto')
router.register(r'molhos', api_views.MolhoViewSet, basename='molho')
router.register(r'carnes', api_views.CarneViewSet, basename='carne')
router.register(r'rondellis', api_views.RondelliViewSet, basename='rondelli')
router.register(r'combos', api_views.ComboViewSet, basename='combo')
router.register(r'carrinho', api_views.CarrinhoViewSet, basename='carrinho')
router.register(r'pedidos', api_views.PedidoViewSet, basename='pedido')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Catalog (combined view for home page)
    path('catalogo/', api_views.CatalogoView.as_view(), name='catalogo'),
    
    # Checkout / Payment
    path('checkout/', api_views.CheckoutView.as_view(), name='checkout'),
    
    # Webhook
    path('webhook/mercadopago/', api_views.mercado_pago_webhook, name='webhook_mercadopago'),
    
    # Auth
    path('auth/register/', api_views.RegisterView.as_view(), name='register'),
    path('auth/profile/', api_views.ProfileView.as_view(), name='profile'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
