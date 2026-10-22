"""Ranking por entregador e por atendente (do admin do Prefiro).

Entregador: quem levou (`StoreOrder.entregador`, atribuído no quadro).
Atendente: quem lançou o pedido no painel/PDV (`created_by_staff`).
Pedido cancelado não conta; frete é o repasse ao entregador e fica fora do
faturado do atendente (`soma_de_venda`).
"""
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.stores.metrics import soma_de_venda
from apps.stores.metrics.definicoes import STATUS_SEM_RECEITA
from apps.stores.models import StoreOrder


def ranking_da_operacao(store, dias: int = 30, agora=None) -> dict:
    agora = agora or timezone.now()
    pedidos = StoreOrder.objects.filter(
        store=store, created_at__gte=agora - timedelta(days=dias), created_at__lte=agora,
    ).exclude(status__in=STATUS_SEM_RECEITA)

    tempo = ExpressionWrapper(F('delivered_at') - F('out_for_delivery_at'), output_field=DurationField())
    entregadores = (
        pedidos.filter(entregador__isnull=False)
        .values('entregador_id', 'entregador__nome')
        .annotate(
            entregas=Count('id'),
            frete=Sum('delivery_fee'),
            tempo_medio=Avg(tempo, filter=Q(delivered_at__isnull=False, out_for_delivery_at__isnull=False)),
        )
        .order_by('-entregas', 'entregador__nome')
    )
    atendentes = (
        pedidos.filter(created_by_staff__isnull=False)
        .values('created_by_staff_id', 'created_by_staff__first_name', 'created_by_staff__username')
        .annotate(pedidos=Count('id'), faturado=soma_de_venda())
        .order_by('-pedidos')
    )
    return {
        'dias': dias,
        'entregadores': [
            {
                'id': str(e['entregador_id']),
                'nome': e['entregador__nome'],
                'entregas': e['entregas'],
                'frete': float(e['frete'] or 0),
                'minutos_medios': round(e['tempo_medio'].total_seconds() / 60) if e['tempo_medio'] else None,
            }
            for e in entregadores
        ],
        'sem_entregador': pedidos.filter(
            entregador__isnull=True, delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
        ).count(),
        'atendentes': _atendentes(store, atendentes),
    }


def _nome(user) -> str:
    return user.first_name or user.username


def _atendentes(store, com_pedido) -> list[dict]:
    """Quem lançou pedido no período + a equipe da loja com zero.

    Sem a equipe, colaborador recém-cadastrado não aparecia ("Nenhum pedido
    lançado no painel") e o dono achava que o cadastro não tinha valido.
    """
    from apps.stores.models import StoreTeamMember

    linhas = {
        a['created_by_staff_id']: {
            'id': a['created_by_staff_id'],
            'nome': a['created_by_staff__first_name'] or a['created_by_staff__username'],
            'pedidos': a['pedidos'],
            'faturado': float(a['faturado'] or 0),
        }
        for a in com_pedido
    }
    equipe = [store.owner] if store.owner_id else []
    equipe += list(store.staff.all())
    equipe += [m.user for m in StoreTeamMember.objects.filter(tenant=store, is_active=True).select_related('user')]
    for user in equipe:
        linhas.setdefault(user.id, {'id': user.id, 'nome': _nome(user), 'pedidos': 0, 'faturado': 0.0})
    return sorted(linhas.values(), key=lambda a: (-a['pedidos'], a['nome'].lower()))
