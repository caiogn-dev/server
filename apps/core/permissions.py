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
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')
        
        if not store_slug:
            store_slug = request.query_params.get('store_slug')
        
        if not store_slug:
            return True
        
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
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')
        
        if not store_slug:
            store_slug = request.query_params.get('store_slug')
        
        if not store_slug:
            return True
        
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
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        if request.user.is_superuser:
            return True
        
        store_slug = view.kwargs.get('store_slug') or view.kwargs.get('slug')
        
        if not store_slug:
            store_slug = request.query_params.get('store_slug')
        
        if not store_slug:
            return True
        
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
    Permission that only allows read-only methods.
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        return request.method in permissions.SAFE_METHODS


class IsWhatsAppAccountOwner(permissions.BasePermission):
    """
    Permission that checks if user owns the WhatsApp account.
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        account_id = view.kwargs.get('account_id')
        
        if not account_id:
            return True
        
        from apps.whatsapp.models import WhatsAppAccount
        
        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return False
        
        return account.owner == request.user
    
    def has_object_permission(self, request: Request, view: View, obj) -> bool:
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'account'):
            return obj.account.owner == request.user
        
        return False


class IsCompanyProfileOwner(permissions.BasePermission):
    """
    Permission that checks if user owns the company profile
    through the linked WhatsApp account or Store.
    """
    
    def has_permission(self, request: Request, view: View) -> bool:
        profile_id = view.kwargs.get('profile_id') or view.kwargs.get('pk')
        
        if not profile_id:
            return True
        
        from apps.automation.models import CompanyProfile
        
        try:
            profile = CompanyProfile.objects.get(id=profile_id, is_active=True)
        except CompanyProfile.DoesNotExist:
            return False
        
        # Check through store
        if profile.store:
            return (
                profile.store.owner == request.user or
                profile.store.staff.filter(id=request.user.id).exists()
            )
        
        # Check through account (legacy)
        if profile.account:
            return profile.account.owner == request.user
        
        return False


__all__ = [
    'IsStoreOwner',
    'IsStoreStaff',
    'HasStoreAccess',
    'IsOwnerOrReadOnly',
    'IsSuperUserOrReadOnly',
    'ReadOnly',
    'IsWhatsAppAccountOwner',
    'IsCompanyProfileOwner',
]
