"""
Audit service for logging user actions.
"""
import logging
from typing import Optional, Dict, Any, List
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet
from django.utils import timezone

from ..models import AuditLog

logger = logging.getLogger(__name__)
User = get_user_model()


class AuditService:
    """Service for audit logging operations."""
    
    def log_action(
        self,
        action: str,
        description: str,
        user: Optional[User] = None,
        obj: Optional[Model] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        module: str = '',
        extra_data: Optional[Dict[str, Any]] = None,
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log an action."""
        content_type = None
        object_id = ''
        object_repr = ''
        
        if obj:
            content_type = ContentType.objects.get_for_model(obj)
            object_id = str(obj.pk)
            object_repr = str(obj)[:255]
        
        changes = {}
        if old_values and new_values:
            changes = self._compute_changes(old_values, new_values)
        
        request_info = request_info or {}
        
        audit_log = AuditLog.objects.create(
            user=user,
            user_email=user.email if user else '',
            user_ip=request_info.get('ip', ''),
            user_agent=request_info.get('user_agent', '')[:500],
            action=action,
            action_description=description,
            content_type=content_type,
            object_id=object_id,
            object_repr=object_repr,
            old_values=old_values or {},
            new_values=new_values or {},
            changes=changes,
            module=module,
            extra_data=extra_data or {},
            request_id=request_info.get('request_id', ''),
            request_path=request_info.get('path', '')[:500],
            request_method=request_info.get('method', '')[:10],
        )
        
        return audit_log
    
    def log_create(
        self,
        obj: Model,
        user: Optional[User] = None,
        module: str = '',
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log object creation."""
        return self.log_action(
            action=AuditLog.ActionType.CREATE,
            description=f"Created {obj._meta.verbose_name}: {obj}",
            user=user,
            obj=obj,
            new_values=self._model_to_dict(obj),
            module=module or obj._meta.app_label,
            request_info=request_info,
        )
    
    def log_update(
        self,
        obj: Model,
        old_values: Dict[str, Any],
        user: Optional[User] = None,
        module: str = '',
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log object update."""
        new_values = self._model_to_dict(obj)
        return self.log_action(
            action=AuditLog.ActionType.UPDATE,
            description=f"Updated {obj._meta.verbose_name}: {obj}",
            user=user,
            obj=obj,
            old_values=old_values,
            new_values=new_values,
            module=module or obj._meta.app_label,
            request_info=request_info,
        )
    
    def log_delete(
        self,
        obj: Model,
        user: Optional[User] = None,
        module: str = '',
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log object deletion."""
        return self.log_action(
            action=AuditLog.ActionType.DELETE,
            description=f"Deleted {obj._meta.verbose_name}: {obj}",
            user=user,
            obj=obj,
            old_values=self._model_to_dict(obj),
            module=module or obj._meta.app_label,
            request_info=request_info,
        )
    
    def log_status_change(
        self,
        obj: Model,
        old_status: str,
        new_status: str,
        user: Optional[User] = None,
        module: str = '',
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log status change."""
        return self.log_action(
            action=AuditLog.ActionType.STATUS_CHANGE,
            description=f"Status changed from '{old_status}' to '{new_status}' for {obj._meta.verbose_name}: {obj}",
            user=user,
            obj=obj,
            old_values={'status': old_status},
            new_values={'status': new_status},
            module=module or obj._meta.app_label,
            request_info=request_info,
        )
    
    def log_login(
        self,
        user: User,
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log user login."""
        return self.log_action(
            action=AuditLog.ActionType.LOGIN,
            description=f"User logged in: {user.email}",
            user=user,
            module='auth',
            request_info=request_info,
        )
    
    def log_logout(
        self,
        user: User,
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log user logout."""
        return self.log_action(
            action=AuditLog.ActionType.LOGOUT,
            description=f"User logged out: {user.email}",
            user=user,
            module='auth',
            request_info=request_info,
        )
    
    def log_export(
        self,
        export_type: str,
        user: Optional[User] = None,
        filters: Optional[Dict[str, Any]] = None,
        record_count: int = 0,
        request_info: Optional[Dict[str, str]] = None,
    ) -> AuditLog:
        """Log data export."""
        return self.log_action(
            action=AuditLog.ActionType.EXPORT,
            description=f"Exported {record_count} {export_type} records",
            user=user,
            module='export',
            extra_data={
                'export_type': export_type,
                'filters': filters or {},
                'record_count': record_count,
            },
            request_info=request_info,
        )
    
    def get_logs(
        self,
        user: Optional[User] = None,
        action: Optional[str] = None,
        module: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        start_date: Optional[timezone.datetime] = None,
        end_date: Optional[timezone.datetime] = None,
        limit: int = 100,
    ) -> QuerySet:
        """Get audit logs with filters."""
        queryset = AuditLog.objects.all()
        
        if user:
            queryset = queryset.filter(user=user)
        
        if action:
            queryset = queryset.filter(action=action)
        
        if module:
            queryset = queryset.filter(module=module)
        
        if object_type:
            content_type = ContentType.objects.filter(model=object_type.lower()).first()
            if content_type:
                queryset = queryset.filter(content_type=content_type)
        
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        return queryset[:limit]
    
    def get_object_history(
        self,
        obj: Model,
        limit: int = 50,
    ) -> QuerySet:
        """Get audit history for a specific object."""
        content_type = ContentType.objects.get_for_model(obj)
        return AuditLog.objects.filter(
            content_type=content_type,
            object_id=str(obj.pk)
        )[:limit]
    
    def get_user_activity(
        self,
        user: User,
        days: int = 30,
        limit: int = 100,
    ) -> QuerySet:
        """Get user activity for the last N days."""
        start_date = timezone.now() - timezone.timedelta(days=days)
        return AuditLog.objects.filter(
            user=user,
            created_at__gte=start_date
        )[:limit]
    
    def _model_to_dict(self, obj: Model) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        data = {}
        for field in obj._meta.fields:
            value = getattr(obj, field.name)
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            elif hasattr(value, 'pk'):
                value = str(value.pk)
            else:
                try:
                    # Try to serialize, skip if not possible
                    import json
                    json.dumps(value)
                except (TypeError, ValueError):
                    value = str(value)
            data[field.name] = value
        return data
    
    def _compute_changes(
        self,
        old_values: Dict[str, Any],
        new_values: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute changes between old and new values."""
        changes = {}
        all_keys = set(old_values.keys()) | set(new_values.keys())
        
        for key in all_keys:
            old_val = old_values.get(key)
            new_val = new_values.get(key)
            
            if old_val != new_val:
                changes[key] = {
                    'old': old_val,
                    'new': new_val,
                }
        
        return changes
