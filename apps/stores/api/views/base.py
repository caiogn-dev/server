"""
Base utilities and permissions for store API views.
"""
import uuid as uuid_module
from rest_framework import permissions
from django.db.models import Q
from apps.stores.models import Store


def filter_by_store(queryset, store_param):
    """Filter queryset by store UUID or slug."""
    if not store_param:
        return queryset, False

    try:
        uuid_module.UUID(store_param)
        return queryset.filter(store_id=store_param), True
    except (ValueError, AttributeError):
        return queryset.filter(store__slug=store_param), True


def filter_by_user(queryset, user):
    """
    Restrict queryset to stores owned or managed by the user.

    Call this *before* filter_by_store so that supplying an arbitrary
    store_id cannot bypass ownership checks.
    """
    if user.is_staff:
        return queryset
    return queryset.filter(Q(store__owner=user) | Q(store__staff=user)).distinct()


class IsStoreOwnerOrStaff(permissions.BasePermission):
    """Permission to check if user owns or manages the store."""
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'store'):
            store = obj.store
        elif isinstance(obj, Store):
            store = obj
        else:
            return False
        
        return (
            store.owner == request.user or
            request.user in store.staff.all() or
            request.user.is_staff
        )


def get_user_stores_queryset(user, queryset_class):
    """Get queryset filtered by user's accessible stores."""
    if user.is_staff:
        return queryset_class.objects.all()
    return queryset_class.objects.filter(
        Q(owner=user) | Q(staff=user)
    ).distinct()
