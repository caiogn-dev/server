"""Portão do adicional Etiqueta ANVISA sobre a API de nutrição.

A API é por usuário, não por loja: várias chamadas do painel não dizem de
qual loja são. Então o portão decide assim:
  - a chamada aponta uma loja (`store`) ou um produto (`product`) → ESSA loja
    precisa ter o adicional;
  - não aponta nenhuma → basta o usuário ter uma loja com o adicional, e os
    querysets (`lojas_liberadas`) escondem o que é das outras.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework.permissions import BasePermission

from apps.core.exceptions import BaseAPIException
from apps.stores import billing
from apps.stores.models import Store, StoreProduct

ADICIONAL = 'etiqueta_anvisa'


class AdicionalNecessario(BaseAPIException):
    status_code = 402
    default_code = 'adicional_necessario'
    default_message = (
        'Contrate o adicional Etiqueta ANVISA para montar receitas e imprimir '
        'etiquetas nutricionais.'
    )


def lojas_liberadas(user, prefixo='store__'):
    """Filtro das lojas do usuário (dono/staff) que têm o adicional."""
    return (
        (Q(**{f'{prefixo}owner': user}) | Q(**{f'{prefixo}staff': user}))
        & billing.q_lojas_com_adicional(ADICIONAL, prefixo)
    )


def _loja_apontada(request):
    """id da loja que a chamada aponta, ou None se não aponta nenhuma."""
    dados = request.data if hasattr(request.data, 'get') else {}
    loja = request.query_params.get('store') or dados.get('store')
    produto = request.query_params.get('product') or dados.get('product')
    try:
        if loja:
            return Store.objects.filter(pk=loja).values_list('pk', flat=True).first()
        if produto:
            return StoreProduct.objects.filter(pk=produto).values_list('store_id', flat=True).first()
    except (ValueError, DjangoValidationError):
        return None  # id malformado: a view responde do jeito dela
    return None


class ExigeAdicionalEtiqueta(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return True  # IsAuthenticated responde o 401
        loja_id = _loja_apontada(request)
        if loja_id and not Store.objects.filter(Q(owner=user) | Q(staff=user), pk=loja_id).exists():
            return True  # loja alheia: a view recusa com o 403/400 de sempre
        minhas = Store.objects.filter(lojas_liberadas(user, prefixo=''))
        liberado = minhas.filter(pk=loja_id).exists() if loja_id else minhas.exists()
        if not liberado:
            raise AdicionalNecessario(details={'adicional': ADICIONAL})
        return True
