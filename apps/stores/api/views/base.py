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


class IsStoreOwnerOrStaff(permissions.BasePermission):
    """Permission to check if user owns or manages the store.

    For nested-router views (store_pk in kwargs) this also enforces
    request-level access so that users cannot list/create resources
    inside a store they don't own.
    """

    def _user_can_access_store(self, user, store):
        return (
            store.owner == user or
            user in store.staff.all() or
            user.is_staff or
            user.is_superuser
        )

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        # Superusers and Django staff bypass store ownership check
        if request.user.is_staff or request.user.is_superuser:
            return True
        # When accessing via nested router (stores/{store_pk}/...), verify ownership
        store_pk = view.kwargs.get('store_pk')
        if store_pk:
            try:
                store = Store.objects.get(pk=store_pk)
            except Store.DoesNotExist:
                return False
            return self._user_can_access_store(request.user, store)
        return True

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'store'):
            store = obj.store
        elif isinstance(obj, Store):
            store = obj
        else:
            return False
        return self._user_can_access_store(request.user, store)


def get_user_stores_queryset(user, queryset_class):
    """Get queryset filtered by user's accessible stores."""
    if user.is_staff:
        return queryset_class.objects.all()
    return queryset_class.objects.filter(
        Q(owner=user) | Q(staff=user)
    ).distinct()
