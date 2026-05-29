"""
Base utilities and permissions for store API views.
"""
import uuid as uuid_module
from rest_framework import permissions
from apps.stores.models import Store
from apps.core.permissions import accessible_store_ids


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
        if user.is_staff or user.is_superuser:
            return True
        if store.owner == user or user in store.staff.all():
            return True
        # Fallback: checar StoreTeamMember com o novo sistema de roles
        from apps.stores.permissions import get_member_role
        if get_member_role(user, store) is not None:
            return True
        return False

    def has_permission(self, request, view):
        import logging
        import sys
        logger = logging.getLogger(__name__)

        # Force print to stderr for debugging
        print(f"[PERM_DEBUG] has_permission called", file=sys.stderr)

        if not (request.user and request.user.is_authenticated):
            logger.warning(f"[IsStoreOwnerOrStaff] User not authenticated: {request.user}")
            print(f"[PERM_DEBUG] User not authenticated", file=sys.stderr)
            return False

        logger.info(f"[IsStoreOwnerOrStaff] User authenticated: {request.user.email}, is_staff={request.user.is_staff}, is_superuser={request.user.is_superuser}")
        print(f"[PERM_DEBUG] User authenticated: {request.user.email}, is_staff={request.user.is_staff}", file=sys.stderr)

        # Superusers and Django staff bypass store ownership check
        if request.user.is_staff or request.user.is_superuser:
            logger.info(f"[IsStoreOwnerOrStaff] User is staff/superuser, ALLOWING access")
            return True

        # When accessing via nested router (stores/{store_pk}/...), verify ownership
        store_pk = view.kwargs.get('store_pk')
        logger.info(f"[IsStoreOwnerOrStaff] store_pk={store_pk}, view.kwargs={view.kwargs}")

        if store_pk:
            try:
                # Try UUID first, then slug
                try:
                    uuid_module.UUID(str(store_pk))
                    store = Store.objects.get(pk=store_pk)
                except ValueError:
                    store = Store.objects.get(slug=store_pk)
            except Store.DoesNotExist:
                logger.warning(f"[IsStoreOwnerOrStaff] Store not found: {store_pk}")
                return False

            can_access = self._user_can_access_store(request.user, store)
            logger.info(f"[IsStoreOwnerOrStaff] Store {store_pk} access check: {can_access}")
            return can_access

        logger.info(f"[IsStoreOwnerOrStaff] No store_pk, ALLOWING access")
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
    store_ids = accessible_store_ids(user)
    return queryset_class.objects.filter(id__in=store_ids)
