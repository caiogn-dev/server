"""
Orders app URL routing.
"""
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.orders.views import OrderDeliveryViewSet

app_name = 'orders'

router = SimpleRouter()
# Register viewset for nested routing: /api/v1/stores/{store_slug}/orders/{id}/create-delivery-request/
# The {store_slug} is passed through URL parameter
router.register(
    r'stores/(?P<store_slug>[\w-]+)/orders',
    OrderDeliveryViewSet,
    basename='order-delivery'
)

urlpatterns = router.urls
