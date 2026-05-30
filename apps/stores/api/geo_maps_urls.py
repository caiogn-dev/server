"""
Global GEO/MAPS endpoints (no store slug required).
Included directly in config/urls.py as path('maps/', include(...))
"""
from django.urls import path
from .maps_views import StoreGeocodeView, StoreReverseGeocodeView, StoreAutosuggestView

urlpatterns = [
    path('geocode/', StoreGeocodeView.as_view(), name='maps-geocode'),
    path('reverse-geocode/', StoreReverseGeocodeView.as_view(), name='maps-reverse-geocode'),
    path('autosuggest/', StoreAutosuggestView.as_view(), name='maps-autosuggest'),
]
