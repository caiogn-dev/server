"""Metrics and monitoring endpoints."""
from django.urls import path
from .health_views import health_check, metrics

urlpatterns = [
    path('', health_check, name='health-check-detailed'),
    path('prometheus/', metrics, name='prometheus-metrics'),
]
