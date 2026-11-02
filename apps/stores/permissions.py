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

    O DONO da loja recebe role 'owner' automaticamente. Nenhuma flag de conta
    concede role: is_staff (acesso ao /admin) e is_superuser NÃO valem
    cross-tenant — senão a conta do dono da plataforma enxerga e edita a loja
    de todo cliente pagante.
    """
    if store.owner_id == user.id:
        return 'owner'
    # Staff M2M é o vínculo antigo, de antes dos papéis: vale como gerente,
    # que é o acesso que essas contas já tinham em todas as telas.
    if store.staff.filter(id=user.id).exists():
        return 'manager'
    from apps.stores.models import StoreTeamMember
    member = StoreTeamMember.objects.filter(
        tenant=store,
        user=user,
        is_active=True,
    ).first()
    return member.role if member else None


def lojas_com_permissao(user, action: str):
    """IDs das lojas em que o usuário pode fazer `action` — a mesma regra de
    `has_store_permission`, para filtrar queryset (26/10: estava à mão em ~15
    telas, sem a equipe). Dono sempre; staff legado como gerente; membro ativo
    se o papel dele tem a ação."""
    from django.db.models import Q
    from apps.stores.models import Store

    if not getattr(user, 'is_authenticated', False):
        return Store.objects.none().values_list('id', flat=True)
    papeis = [p for p, acoes in ROLE_PERMISSIONS.items() if action in acoes and p != 'owner']
    regra = Q(owner=user) | Q(
        storeteammember_set__user=user,
        storeteammember_set__is_active=True,
        storeteammember_set__role__in=papeis,
    )
    if action in ROLE_PERMISSIONS['manager']:
        regra |= Q(staff=user)
    return Store.objects.filter(regra).distinct().values_list('id', flat=True)


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
