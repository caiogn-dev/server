"""
Multi-tenant API views and mixins.
"""
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied


class TenantPermission(permissions.BasePermission):
    """
    Permission that checks tenant access.
    """
    
    def has_permission(self, request, view):
        # Allow safe methods for public endpoints
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check if user has access to tenant
        tenant = getattr(request, 'tenant', None)
        if tenant:
            return tenant.owner == request.user or request.user in tenant.staff.all()
        
        return False
    
    def has_object_permission(self, request, view, obj):
        # Check if object belongs to user's tenant
        tenant = getattr(request, 'tenant', None)
        if tenant and hasattr(obj, 'tenant'):
            return obj.tenant == tenant
        return True


class TenantViewSetMixin:
    """
    Mixin for viewsets that automatically filter by tenant.
    """
    
    def get_queryset(self):
        """Filter queryset by tenant from request."""
        queryset = super().get_queryset()
        
        if hasattr(self.request, 'tenant') and self.request.tenant:
            if hasattr(queryset.model, 'tenant'):
                queryset = queryset.filter(tenant=self.request.tenant)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set tenant and user on creation."""
        data = {}
        
        # Set tenant from request
        if hasattr(self.request, 'tenant') and self.request.tenant:
            if hasattr(serializer.Meta.model, 'tenant'):
                data['tenant'] = self.request.tenant
        
        # Set created_by
        if hasattr(serializer.Meta.model, 'created_by'):
            data['created_by'] = self.request.user
        
        serializer.save(**data)
    
    def perform_update(self, serializer):
        """Set updated_by on update."""
        data = {}
        
        if hasattr(serializer.Meta.model, 'updated_by'):
            data['updated_by'] = self.request.user
        
        serializer.save(**data)


class MultiTenantModelViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    """
    Base viewset for multi-tenant models.
    
    Automatically:
    - Filters queryset by tenant
    - Sets tenant on create
    - Sets created_by/updated_by
    - Checks tenant permissions
    """
    permission_classes = [permissions.IsAuthenticated, TenantPermission]
