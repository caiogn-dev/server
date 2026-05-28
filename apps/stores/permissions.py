"""
Sistema de permissões por role para lojas.

Uso:
    from apps.stores.permissions import has_store_permission, get_member_role

    if not has_store_permission(request.user, store, 'team'):
        raise PermissionDenied()
"""
from django.core.exceptions import PermissionDenied

# Mapa de permissões por role
ROLE_PERMISSIONS: dict[str, set[str]] = {
    'owner':    {'catalog', 'orders', 'cancel_order', 'reports', 'team', 'whatsapp', 'config'},
    'manager':  {'catalog', 'orders', 'cancel_order', 'reports', 'whatsapp'},
    'operator': {'orders', 'reports'},
    'viewer':   {'reports'},
}


def get_member_role(user, store) -> str | None:
    """
    Retorna o role do usuário na loja, ou None se não for membro.

    Superusers e staff Django recebem role 'owner' automaticamente.
    """
    if user.is_superuser or user.is_staff:
        return 'owner'
    from apps.stores.models import StoreTeamMember
    member = StoreTeamMember.objects.filter(
        tenant=store,
        user=user,
        is_active=True,
    ).first()
    return member.role if member else None


def has_store_permission(user, store, action: str) -> bool:
    """
    Retorna True se o usuário tem permissão para realizar a ação na loja.

    Args:
        user: Django User
        store: instância de Store
        action: string de ação (ex: 'orders', 'team', 'config')
    """
    role = get_member_role(user, store)
    if not role:
        return False
    return action in ROLE_PERMISSIONS.get(role, set())


def require_store_permission(action: str):
    """
    Decorator para ViewSet que exige permissão de role.

    O ViewSet precisa implementar get_store() retornando a instância de Store.

    Uso:
        @require_store_permission('team')
        def create(self, request, *args, **kwargs):
            ...
    """
    def decorator(view_func):
        def wrapper(self, request, *args, **kwargs):
            store = self.get_store()
            if not has_store_permission(request.user, store, action):
                raise PermissionDenied(
                    f"Você não tem permissão para realizar '{action}' nesta loja."
                )
            return view_func(self, request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        wrapper.__doc__ = view_func.__doc__
        return wrapper
    return decorator
