"""
URLs para Handover Protocol
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HandoverViewSet, HandoverRequestViewSet, HandoverLogViewSet

app_name = 'handover'

router = DefaultRouter()
router.register(r'requests', HandoverRequestViewSet, basename='handover-request')
router.register(r'logs', HandoverLogViewSet, basename='handover-log')

urlpatterns = [
    # Handover actions em conversas
    path('conversations/<uuid:pk>/handover/bot/', 
         HandoverViewSet.as_view({'post': 'bot'}), 
         name='handover-bot'),
    
    path('conversations/<uuid:pk>/handover/human/', 
         HandoverViewSet.as_view({'post': 'human'}), 
         name='handover-human'),
    
    path('conversations/<uuid:pk>/handover/status/', 
         HandoverViewSet.as_view({'get': 'status'}), 
         name='handover-status'),
    
    path('conversations/<uuid:pk>/handover/logs/', 
         HandoverViewSet.as_view({'get': 'logs'}), 
         name='handover-logs'),
    
    path('conversations/<uuid:pk>/handover/request/', 
         HandoverViewSet.as_view({'post': 'request'}), 
         name='handover-request-create'),
    
    # Router URLs
    path('', include(router.urls)),
]
