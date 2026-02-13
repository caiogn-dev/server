"""
Base utilities and pagination for automation API views.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API results."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
