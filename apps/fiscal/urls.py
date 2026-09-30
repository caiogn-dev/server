"""Rotas da página de Notas — incluídas em /api/v1/stores/{store_slug}/fiscal/."""
from django.urls import path

from . import views

urlpatterns = [
    path('notas/', views.NotasView.as_view(), name='fiscal-notas'),
    path('notas/emitir/', views.EmitirNotaView.as_view(), name='fiscal-notas-emitir'),
    path('notas/<uuid:pk>/cancelar/', views.CancelarNotaView.as_view(), name='fiscal-notas-cancelar'),
    path('notas/<uuid:pk>/enviar-email/', views.EnviarNotaPorEmailView.as_view(), name='fiscal-notas-enviar-email'),
    path('destinatarios/', views.DestinatariosView.as_view(), name='fiscal-destinatarios'),
    path('destinatarios/<uuid:pk>/', views.DestinatarioView.as_view(), name='fiscal-destinatario'),
    path('pedidos/', views.PedidosParaNotaView.as_view(), name='fiscal-pedidos'),
    path('cnpj/<str:cnpj>/', views.ConsultaCnpjView.as_view(), name='fiscal-cnpj'),
]
