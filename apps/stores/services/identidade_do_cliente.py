"""Todo cliente da loja tem identidade (UnifiedUser) — 28/10.

A busca do novo pedido lê UnifiedUser. Cliente da loja (StoreCustomer) sem
identidade não aparece lá: foi o HOA COMERCIO, duas vezes. A garantia morava
no serializer da tela Clientes; agora mora no `save()` do modelo, por onde
passam todos os caminhos que criam cliente.
"""
import logging

logger = logging.getLogger(__name__)


def nome_do_cadastro(customer) -> str:
    """Empresa pelo nome que se fala (fantasia), senão a razão social; pessoa pelo nome."""
    nome = (customer.nome_fantasia or customer.razao_social or '').strip()
    if not nome and customer.user_id:
        nome = (customer.user.get_full_name() or customer.user.first_name or '').strip()
    return nome


def ligar_identidade(customer) -> bool:
    """Liga o cliente à identidade pelo telefone/login. Devolve se ligou."""
    from apps.stores.models import StoreCustomer
    from apps.users.models import UnifiedUser

    if customer.unified_user_id or not customer.phone:
        return False
    email = ''
    if customer.user_id and customer.user.email and not customer.user.email.endswith(('.invalid', '.local')):
        email = customer.user.email
    try:
        uu, _ = UnifiedUser.resolve(
            phone=customer.phone, email=email,
            name=nome_do_cadastro(customer) or 'Cliente',
            django_user=customer.user if customer.user_id else None,
        )
    except ValueError:
        logger.warning('cliente %s sem identidade: telefone inválido', customer.pk)
        return False
    # update() e não save(): não reentrar no save() do modelo.
    StoreCustomer.objects.filter(pk=customer.pk).update(unified_user=uu)
    customer.unified_user = uu
    return True


def ligar_orfaos() -> int:
    """Liga todos os clientes ainda sem identidade. Idempotente; devolve quantos ligou."""
    from apps.stores.models import StoreCustomer

    orfaos = (StoreCustomer.objects
              .filter(unified_user__isnull=True)
              .exclude(phone='')
              .select_related('user'))
    return sum(1 for c in orfaos if ligar_identidade(c))
