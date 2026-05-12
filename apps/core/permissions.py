"""
Core permission classes for Pastita Platform.

These permissions ensure users can only access data they own or are authorized to manage.
"""
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import View


class IsStoreOwner(permissions.BasePermission):
    """
    Permission that checks if the user is the owner of the store.
    Returns False (instead of True) when no store_slug is present to prevent bypass.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')

        if not store_slug:
            store_slug = request.query_params.get('store_slug')

        if not store_slug:
            return False

        from apps.stores.models import Store

        try:
            store = Store.objects.get(slug=store_slug, is_active=True)
        except Store.DoesNotExist:
            return False

        return store.owner == request.user

    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        if hasattr(obj, 'store'):
            return obj.store.owner == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user

        return False


class IsStoreStaff(permissions.BasePermission):
    """
    Permission that checks if the user is staff (owner or team member) of the store.
    Returns False (instead of True) when no store_slug is present to prevent bypass.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')

        if not store_slug:
            store_slug = request.query_params.get('store_slug')

        if not store_slug:
            return False

        from apps.stores.models import Store

        try:
            store = Store.objects.get(slug=store_slug, is_active=True)
        except Store.DoesNotExist:
            return False

        return (
            store.owner == request.user or
            store.staff.filter(id=request.user.id).exists()
        )

    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        if hasattr(obj, 'store'):
            store = obj.store
            return (
                store.owner == request.user or
                store.staff.filter(id=request.user.id).exists()
            )
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user

        return False


class HasStoreAccess(permissions.BasePermission):
    """
    Permission that checks if user has any access to the store
    (owner, staff, or superuser).
    Returns False (instead of True) when no store_slug is present to prevent bypass.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        if request.user.is_superuser:
            return True

        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')

        if not store_slug:
            store_slug = request.query_params.get('store_slug')

        if not store_slug:
            return False

        from apps.stores.models import Store

        try:
            store = Store.objects.get(slug=store_slug, is_active=True)
        except Store.DoesNotExist:
            return False

        return (
            store.owner == request.user or
            store.staff.filter(id=request.user.id).exists()
        )

    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        if request.user.is_superuser:
            return True

        if hasattr(obj, 'store'):
            store = obj.store
            return (
                store.owner == request.user or
                store.staff.filter(id=request.user.id).exists()
            )
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user

        return False


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission that allows read-only access to anyone,
    but only the owner can modify.
    """

    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True

        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'store'):
            return obj.store.owner == request.user

        return False


class IsSuperUserOrReadOnly(permissions.BasePermission):
    """
    Permission that allows read-only access to anyone,
    but only superusers can modify.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_superuser


class ReadOnly(permissions.BasePermission):
    """
    Permission that only allows read-only access.
    """

    def has_permission(self, request: Request, view: View) -> bool:
        return request.method in permissions.SAFE_METHODS
