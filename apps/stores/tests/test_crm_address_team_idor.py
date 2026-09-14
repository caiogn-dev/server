"""Regressão P1: IDOR de leitura em CustomerAddressViewSet e TeamMemberViewSet.

IsStoreOwnerOrStaff.has_permission() retorna True incondicionalmente quando
`store_pk` NÃO está em view.kwargs. As rotas de CRM (crm/customers/.../addresses/
e team/) usam `store_slug`, não `store_pk` — portanto o gate nunca executava.

Vetor confirmado:
  Atacante autenticado com loja própria chama:
    GET /api/v1/stores/{slug-da-vítima}/crm/customers/{uuid}/addresses/
    GET /api/v1/stores/{slug-da-vítima}/team/
  e lê endereços de clientes e membros da equipe de qualquer tenant sem ter
  acesso à loja da vítima.

Correção: gate explícito em get_queryset() de ambas as ViewSets via
user_can_access_store(), com Http404 (info-hiding).
"""
from django.test import SimpleTestCase


# ─── análise estática (sem banco) ───────────────────────────────────────────

class CustomerAddressViewSetStaticTest(SimpleTestCase):
    """A fonte deve conter o gate de tenant em get_queryset."""

    def _source(self):
        import inspect
        from apps.stores.api.views.crm_views import CustomerAddressViewSet
        return inspect.getsource(CustomerAddressViewSet.get_queryset)

    def test_get_queryset_tem_gate_de_acesso(self):
        """get_queryset deve chamar user_can_access_store ou função equivalente."""
        src = self._source()
        self.assertTrue(
            'user_can_access_store' in src or 'has_store_permission' in src,
            "CustomerAddressViewSet.get_queryset() não tem gate de acesso ao tenant. "
            "Qualquer autenticado pode listar endereços de clientes de qualquer loja.",
        )

    def test_get_queryset_protege_usuario_nao_autorizado(self):
        """O gate deve bloquear quem não tem acesso (Http404 ou PermissionDenied)."""
        src = self._source()
        bloqueios = ['Http404', 'raise Http404', 'PermissionDenied',
                     'raise PermissionDenied', 'raise_exception']
        self.assertTrue(
            any(b in src for b in bloqueios),
            "CustomerAddressViewSet.get_queryset() não levanta Http404/PermissionDenied "
            "para usuários sem acesso ao tenant.",
        )

    def test_nao_apenas_filtra_por_tenant_sem_gate(self):
        """Filtrar queryset por tenant SEM verificar acesso ao tenant ainda é IDOR."""
        src = self._source()
        # Se só tem 'filter(unified_user=user, tenant=store)' sem qualquer
        # verificação de acesso, o IDOR persiste.
        self.assertFalse(
            'is_superuser' not in src and 'user_can_access_store' not in src
            and 'has_store_permission' not in src,
            "get_queryset apenas filtra por tenant mas não verifica se o usuário "
            "tem acesso a esse tenant — ainda é IDOR.",
        )


class TeamMemberViewSetStaticTest(SimpleTestCase):
    """A fonte deve conter o gate de tenant em get_queryset."""

    def _source(self):
        import inspect
        from apps.stores.api.views.crm_views import TeamMemberViewSet
        return inspect.getsource(TeamMemberViewSet.get_queryset)

    def test_get_queryset_tem_gate_de_acesso(self):
        """get_queryset deve verificar acesso ao tenant antes de retornar dados."""
        src = self._source()
        self.assertTrue(
            'user_can_access_store' in src or 'has_store_permission' in src,
            "TeamMemberViewSet.get_queryset() não tem gate de acesso ao tenant. "
            "Qualquer autenticado pode listar membros de equipe de qualquer loja.",
        )

    def test_get_queryset_protege_usuario_nao_autorizado(self):
        """O gate deve bloquear quem não tem acesso."""
        src = self._source()
        bloqueios = ['Http404', 'raise Http404', 'PermissionDenied',
                     'raise PermissionDenied']
        self.assertTrue(
            any(b in src for b in bloqueios),
            "TeamMemberViewSet.get_queryset() não levanta Http404/PermissionDenied "
            "para usuários sem acesso ao tenant.",
        )


class IsStoreOwnerOrStaffStaticTest(SimpleTestCase):
    """Documenta o comportamento-raiz do bug: has_permission retorna True
    incondicionalmente quando store_pk não está nos kwargs."""

    def test_has_permission_retorna_true_sem_store_pk(self):
        """has_permission retorna True para store_slug sem store_pk — gate ausente."""
        import inspect
        from apps.stores.api.views.base import IsStoreOwnerOrStaff
        src = inspect.getsource(IsStoreOwnerOrStaff.has_permission)

        # O comportamento vulnerável: se store_pk não existe → return True
        # Isso é intencional para rotas não-nested, mas rotas de CRM precisam
        # de gate próprio em get_queryset.
        self.assertIn(
            'store_pk',
            src,
            "has_permission deve verificar store_pk — se ausente, gate precisa estar em get_queryset.",
        )

    def test_crm_views_nao_dependem_so_do_gate_da_permission_class(self):
        """CustomerAddressViewSet e TeamMemberViewSet não usam store_pk → precisam
        de gate próprio em get_queryset, não apenas na permission class."""
        import inspect
        from apps.stores.api.views.crm_views import CustomerAddressViewSet, TeamMemberViewSet

        for cls in (CustomerAddressViewSet, TeamMemberViewSet):
            src_qs = inspect.getsource(cls.get_queryset)
            uses_store_pk = 'store_pk' in src_qs
            has_own_gate = 'user_can_access_store' in src_qs or 'has_store_permission' in src_qs
            self.assertTrue(
                uses_store_pk or has_own_gate,
                f"{cls.__name__}.get_queryset() não tem gate próprio e não usa "
                f"store_pk — IDOR de leitura cross-tenant.",
            )
