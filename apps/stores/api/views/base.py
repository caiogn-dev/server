"""
Base utilities and permissions for store API views.
"""
import logging
import uuid as uuid_module
from rest_framework import permissions
from apps.stores.models import Store
from apps.core.permissions import accessible_store_ids, user_can_access_store

logger = logging.getLogger(__name__)


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
        # is_staff NÃO concede acesso cross-tenant (só superuser); owner, staff
        # M2M legado e StoreTeamMember ativo são checados em user_can_access_store.
        return user_can_access_store(user, store)

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_superuser:
            return True

        # When accessing via nested router (stores/{store_pk}/...), verify ownership
        store_pk = view.kwargs.get('store_pk')

        if store_pk:
            try:
                try:
                    uuid_module.UUID(str(store_pk))
                    store = Store.objects.get(pk=store_pk)
                except ValueError:
                    store = Store.objects.get(slug=store_pk)
            except Store.DoesNotExist:
                logger.warning("IsStoreOwnerOrStaff: store not found: %s", store_pk)
                return False

            return self._user_can_access_store(request.user, store)

        return True

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Store):
            store = obj
        elif getattr(obj, 'store', None) is not None:
            store = obj.store
        # Objetos filhos sem .store direto (ex.: StoreProductVariant → product.store)
        elif getattr(obj, 'product', None) is not None and getattr(obj.product, 'store', None) is not None:
            store = obj.product.store
        else:
            return False
        return self._user_can_access_store(request.user, store)


def get_user_stores_queryset(user, queryset_class):
    """Get queryset filtered by user's accessible stores.

    Só superuser vê todas; is_staff NÃO vaza cross-tenant.
    """
    if user.is_superuser:
        return queryset_class.objects.all()
    store_ids = accessible_store_ids(user)
    return queryset_class.objects.filter(id__in=store_ids)
